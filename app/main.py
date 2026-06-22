"""FastAPI uygulaması — Web UI için genişletilmiş API yüzeyi.

Deterministik çekirdek (health + manifesto) + planlama CRUD + pasaport
yükleme + ayarlar yönetimi + istatistik dashboard endpoint'leri.
"""
from __future__ import annotations

import shutil
import tempfile
import datetime as _dt
import os
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app import settings as settings_mod
from app import weather as weather_mod
from app.db import connect, init_db
from app.manifest.planning import (
    PlanningRow,
    ReservationBlock,
    read_blocks,
    read_rows,
    balloon_load as planning_balloon_load,
    assign_balloon as planning_assign_balloon,
    pilot_for_balloon as planning_pilot_for_balloon,
    create_reservation as planning_create_reservation,
    delete_reservation as planning_delete_reservation,
    list_sheets as planning_list_sheets,
    create_day_sheet as planning_create_day_sheet,
    write_identity as planning_write_identity,
    write_operation_details as planning_write_operation_details,
)
from app.manifest.writer import ManifestRow, build_rows, export, write_manifest
from app.vision.extractor import PassportRecord, process_image, media_type_for
from app.validation.flags import Flag, ValidationOutcome

app = FastAPI(title="Balon Manifesto Sistemi", version="0.1.0")

# --- CORS: geliştirme ortamında tüm origin'lere izin ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _no_cache_static(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/assets/") or path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ═════════════════════════════════════════════════════════════════════
#  Başlangıç
# ═════════════════════════════════════════════════════════════════════

@app.on_event("startup")
def _startup() -> None:
    """DB şemasını uygula (yoksa oluştur)."""
    init_db()
    weather_mod.start_weather_worker()


# ═════════════════════════════════════════════════════════════════════
#  Yardımcı fonksiyonlar
# ═════════════════════════════════════════════════════════════════════

def _load_settings() -> settings_mod.Settings:
    """Her istekte güncel ayarları oku (dosya dışarıdan değişmiş olabilir)."""
    return settings_mod.load()


def _resolve_planning_path(s: settings_mod.Settings) -> Path:
    """Google Sheets modundaysa xlsx'i indir, değilse doğrudan yolu döndür."""
    if s.uses_google_sheets():
        from app import google_sheets as gs
        return gs.download_as_xlsx(s)
    return s.planning_path()


def _backup_excel(path: Path) -> Path:
    """Yazma işlemi öncesi Excel dosyasını zaman damgalı yedekle."""
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_suffix(f".backup_{ts}.xlsx")
    shutil.copy2(path, backup)
    return backup


def _mask_api_key(key: str) -> str:
    """API anahtarının sadece son 4 karakterini göster, geri kalanını maskele."""
    if not key or len(key) <= 4:
        return key
    return "*" * (len(key) - 4) + key[-4:]


def _block_to_dict(block: ReservationBlock) -> dict:
    """ReservationBlock → JSON-serializable dict (label dâhil)."""
    return {
        "lead_row": block.lead_row,
        "rows": block.rows,
        "pax": block.pax,
        "room": block.room,
        "agency": block.agency,
        "reserved_by": block.reserved_by,
        "company": block.company,
        "balloon": block.balloon,
        "pilot": block.pilot,
        "note": block.note,
        "driver": block.driver,
        "coming_place": block.coming_place,
        "hotel": block.hotel,
        "pickup": block.pickup,
        "lead_name": block.lead_name,
        "passengers": [
            {
                "row": p.row,
                "nationality": p.nationality,
                "sex": p.sex,
                "name": p.name,
                "passport_no": p.passport_no,
            }
            for p in block.passengers
        ],
        "label": block.label(),
    }


# ═════════════════════════════════════════════════════════════════════
#  Health
# ═════════════════════════════════════════════════════════════════════

@app.get("/health")
def health() -> dict:
    """Servis sağlık kontrolü."""
    return {"status": "ok", "version": app.version}


@app.post("/api/app/shutdown")
def api_app_shutdown() -> dict:
    def _exit() -> None:
        os._exit(0)

    threading.Timer(0.25, _exit).start()
    return {"success": True, "message": "Balon Manifesto kapatiliyor."}


# ═════════════════════════════════════════════════════════════════════
#  Ayarlar (Settings)
# ═════════════════════════════════════════════════════════════════════

@app.get("/api/settings")
def get_settings() -> dict:
    """Mevcut ayarları döndür (API anahtarı maskelenmiş)."""
    s = _load_settings()
    data = asdict(s)
    # API anahtarını güvenlik için maskele
    data["anthropic_api_key"] = _mask_api_key(s.anthropic_api_key)
    data["weather_api_key"] = _mask_api_key(s.weather_api_key)
    # Türetilmiş bilgileri de ekle
    data["_derived"] = {
        "planning_path": str(s.planning_path()),
        "template_path": str(s.template_path()),
        "output_path": str(s.output_path()),
        "uses_claude": s.uses_claude(),
        "has_api_key": s.has_api_key(),
        "uses_google_sheets": s.uses_google_sheets(),
        "google_is_configured": s.google_is_configured(),
    }
    return data


@app.put("/api/settings")
def update_settings(body: dict) -> dict:
    """Ayarları güncelle, doğrula ve kaydet. Güncel halini döndür."""
    current = _load_settings()
    current_dict = asdict(current)

    # Gelen alanlarla mevcut ayarları birleştir
    for key in settings_mod.Settings.__dataclass_fields__:
        if key in body:
            # API anahtarı maskeliyse (yıldızlı) eskisini koru
            if key == "anthropic_api_key" and body[key] and "*" in body[key]:
                continue
            if key == "weather_api_key" and body[key] and "*" in body[key]:
                continue
            current_dict[key] = body[key]

    try:
        updated = settings_mod.Settings(**{
            k: current_dict[k]
            for k in settings_mod.Settings.__dataclass_fields__
            if k in current_dict
        }).normalized()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Ayar doğrulama hatası: {e}")

    # Kaydet
    settings_mod.save(updated)

    # Maskelenmiş haliyle dön
    data = asdict(updated)
    data["anthropic_api_key"] = _mask_api_key(updated.anthropic_api_key)
    data["weather_api_key"] = _mask_api_key(updated.weather_api_key)
    data["_derived"] = {
        "planning_path": str(updated.planning_path()),
        "template_path": str(updated.template_path()),
        "output_path": str(updated.output_path()),
        "uses_claude": updated.uses_claude(),
        "has_api_key": updated.has_api_key(),
        "uses_google_sheets": updated.uses_google_sheets(),
        "google_is_configured": updated.google_is_configured(),
    }
    return data


# ═════════════════════════════════════════════════════════════════════
#  Listeler (kalıcı referans verisi: balon/otel/şoför/acente/pilot)
# ═════════════════════════════════════════════════════════════════════

# operation_options altında tutulan, değer-listesi destekli kategoriler
LIST_CATEGORIES = ("hotel", "driver", "agency", "pilot", "coming_place", "reserved_by")


def _lists_payload(s: settings_mod.Settings) -> dict:
    return {
        "balloons": list(s.balloon_codes),
        "capacity": s.balloon_capacity,
        "options": {cat: list(s.operation_options.get(cat, [])) for cat in LIST_CATEGORIES},
    }


def _remember_values(s: settings_mod.Settings, fields: dict) -> bool:
    """Operasyon alanlarından gelen yeni değerleri kalıcı listelere ekler.

    Dönüş: herhangi bir değer eklendiyse True (çağıran kaydeder).
    """
    changed = False
    for cat in LIST_CATEGORIES:
        val = str(fields.get(cat, "")).strip()
        if not val:
            continue
        bucket = s.operation_options.setdefault(cat, [])
        if val.upper() not in {v.upper() for v in bucket}:
            bucket.append(val)
            changed = True
    return changed


@app.get("/api/lists")
def api_lists_get() -> dict:
    """Kayıtlı tüm listeleri döndür (balonlar + operasyon değer listeleri)."""
    return _lists_payload(_load_settings())


@app.get("/api/countries")
def api_countries() -> dict:
    """Uyruk otomatik tamamlama için alpha-3 kod + ad listesi (country_map)."""
    from app.country.country_map import load as load_country_map
    data = load_country_map()
    items = sorted(
        ({"code": v["code"], "name": v["name"]} for v in data.values()),
        key=lambda x: x["code"],
    )
    return {"countries": items}


@app.post("/api/lists/add")
def api_lists_add(body: dict) -> dict:
    """Bir kategoriye değer ekle (balon kodu ya da otel/şoför/acente/pilot/geleceği yer)."""
    category = str(body.get("category", "")).strip()
    value = str(body.get("value", "")).strip()
    if not value:
        raise HTTPException(status_code=422, detail="value alanı boş olamaz.")

    s = _load_settings()
    if category == "balloon":
        s.balloon_codes.append(value)
    elif category in LIST_CATEGORIES:
        s.operation_options.setdefault(category, []).append(value)
    else:
        raise HTTPException(status_code=422, detail=f"Geçersiz kategori: {category}")

    s = s.normalized()
    settings_mod.save(s)
    return _lists_payload(s)


@app.post("/api/lists/delete")
def api_lists_delete(body: dict) -> dict:
    """Bir kategoriden değeri sil (büyük/küçük harf duyarsız)."""
    category = str(body.get("category", "")).strip()
    value = str(body.get("value", "")).strip()
    if not value:
        raise HTTPException(status_code=422, detail="value alanı boş olamaz.")

    s = _load_settings()
    target = value.upper()
    if category == "balloon":
        s.balloon_codes = [c for c in s.balloon_codes if c.upper() != target]
    elif category in LIST_CATEGORIES:
        s.operation_options[category] = [
            v for v in s.operation_options.get(category, []) if v.upper() != target
        ]
    else:
        raise HTTPException(status_code=422, detail=f"Geçersiz kategori: {category}")

    s = s.normalized()
    settings_mod.save(s)
    return _lists_payload(s)


# ═════════════════════════════════════════════════════════════════════
#  Planlama (Planning)
# ═════════════════════════════════════════════════════════════════════

@app.get("/api/planning/sheets")
def api_planning_sheets() -> dict:
    """Planlama dosyasındaki gün sayfalarını listele."""
    s = _load_settings()
    try:
        if s.uses_google_sheets():
            from app import google_sheets as gs
            sheets = gs.list_sheets(s)
            source = "google_sheets"
        else:
            xlsx_path = s.planning_path()
            if not xlsx_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Planlama dosyası bulunamadı: {xlsx_path}",
                )
            sheets = planning_list_sheets(xlsx_path)
            source = "excel"
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sayfalar okunamadı: {e}")

    return {"sheets": sheets, "source": source}


@app.get("/api/planning/load")
def api_planning_load(sheet: str = Query(..., description="Gün sayfa adı")) -> dict:
    """Belirli bir gün sayfasının rezervasyon bloklarını yükle."""
    s = _load_settings()
    try:
        xlsx_path = _resolve_planning_path(s)
        blocks = read_blocks(xlsx_path, sheet)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sayfa yüklenemedi: {e}")

    # Balon kodları: Settings rosterü + sayfada görülenlerin birleşimi
    seen_codes = {b.balloon for b in blocks if b.balloon}
    balloon_codes = list(s.balloon_codes)
    for code in sorted(seen_codes):
        if code not in balloon_codes:
            balloon_codes.append(code)

    load = planning_balloon_load(blocks)

    return {
        "sheet": sheet,
        "blocks": [_block_to_dict(b) for b in blocks],
        "balloon_codes": balloon_codes,
        "balloon_load": load,
        "capacity": s.balloon_capacity,
        "total_blocks": len(blocks),
    }


@app.post("/api/planning/create-day")
def api_planning_create_day(body: dict) -> dict:
    """Yeni gün sayfası oluştur (kaynak sayfayı kopyala, verileri temizle)."""
    new_sheet = body.get("new_sheet", "").strip()
    source_sheet = body.get("source_sheet", "").strip() or None

    if not new_sheet:
        raise HTTPException(status_code=422, detail="new_sheet alanı gerekli.")

    s = _load_settings()
    try:
        if s.uses_google_sheets():
            from app import google_sheets as gs
            gs.create_day_sheet(s, new_sheet, source_sheet)
        else:
            xlsx_path = s.planning_path()
            if not xlsx_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Planlama dosyası bulunamadı: {xlsx_path}",
                )
            # Yazma öncesi yedek al
            _backup_excel(xlsx_path)
            planning_create_day_sheet(xlsx_path, new_sheet, source_sheet)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sayfa oluşturulamadı: {e}")

    return {"success": True, "message": f"'{new_sheet}' sayfası oluşturuldu."}


@app.post("/api/planning/create-block")
def api_planning_create_block(body: dict) -> dict:
    """Yeni rezervasyon bloğu ekle; balonu PAX'a göre otomatik ata (first-fit).

    body: {"sheet": "...", "pax": 5, "agency": "...", "hotel": "...", "pickup": "...",
           "room": "...", "reserved_by": "...", "note": "...", "driver": "..."}
    """
    sheet = body.get("sheet", "").strip()
    if not sheet:
        raise HTTPException(status_code=422, detail="sheet alanı gerekli.")
    try:
        pax = int(body.get("pax"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="pax tam sayı olmalı.")
    if not (1 <= pax <= config.MAX_PAX):
        raise HTTPException(status_code=422, detail=f"pax 1–{config.MAX_PAX} aralığında olmalı.")

    lead_fields = {
        k: str(body.get(k, "")).strip()
        for k in ("agency", "hotel", "pickup", "room", "reserved_by", "note", "driver")
        if body.get(k)
    }

    s = _load_settings()
    if s.uses_google_sheets():
        raise HTTPException(
            status_code=400,
            detail="Rezervasyon oluşturma şu an yalnızca Excel modunda destekleniyor.",
        )

    xlsx_path = s.planning_path()
    if not xlsx_path.exists():
        raise HTTPException(status_code=404, detail=f"Planlama dosyası bulunamadı: {xlsx_path}")

    try:
        blocks = read_blocks(xlsx_path, sheet)
        rows = read_rows(xlsx_path, sheet)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sayfa okunamadı: {e}")

    load = planning_balloon_load(blocks)
    balloon, overflow = planning_assign_balloon(load, pax, s.balloon_codes, s.balloon_capacity)
    if not balloon:
        raise HTTPException(status_code=409, detail="Tanımlı balon kodu yok (Settings).")
    pilot = planning_pilot_for_balloon(rows, balloon)

    try:
        _backup_excel(xlsx_path)
        result = planning_create_reservation(
            xlsx_path, sheet, pax=pax, balloon=balloon, pilot=pilot, fields=lead_fields,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rezervasyon yazılamadı: {e}")

    # Yeni otel/acente/şoför değerlerini kalıcı listelere öğret
    if _remember_values(s, lead_fields):
        settings_mod.save(s.normalized())

    new_load = dict(load)
    new_load[balloon] = new_load.get(balloon, 0) + pax
    return {
        "success": True,
        "balloon": balloon,
        "pilot": pilot,
        "overflow": overflow,
        "lead_row": result["lead_row"],
        "rows": result["rows"],
        "capacity": s.balloon_capacity,
        "load": new_load,
        "message": (
            f"{pax} kişilik rezervasyon {balloon} balonuna atandı "
            f"({new_load[balloon]}/{s.balloon_capacity})."
            + (" ⚠ Tüm balonlar dolu, en boş balona yerleştirildi." if overflow else "")
        ),
    }


@app.post("/api/planning/delete-block")
def api_planning_delete_block(body: dict) -> dict:
    """Bir rezervasyon bloğunu sil (satırlarını temizle)."""
    sheet = body.get("sheet", "").strip()
    rows = body.get("rows", [])
    if not sheet:
        raise HTTPException(status_code=422, detail="sheet alanı gerekli.")
    if not rows:
        raise HTTPException(status_code=422, detail="rows listesi boş olamaz.")
    try:
        rows = [int(r) for r in rows]
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Geçersiz satır numarası.")

    s = _load_settings()
    if s.uses_google_sheets():
        raise HTTPException(status_code=400, detail="Silme şu an yalnızca Excel modunda.")
    xlsx_path = s.planning_path()
    if not xlsx_path.exists():
        raise HTTPException(status_code=404, detail=f"Planlama dosyası bulunamadı: {xlsx_path}")
    try:
        _backup_excel(xlsx_path)
        planning_delete_reservation(xlsx_path, sheet, rows)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rezervasyon silinemedi: {e}")
    return {"success": True, "message": f"{len(rows)} satırlık rezervasyon silindi."}


@app.post("/api/planning/write-identity")
def api_planning_write_identity(body: dict) -> dict:
    """Kimlik kolonlarını (uyruk, cinsiyet, isim, pasaport no) güncelle.

    body: {"sheet": "22.06.2026", "updates": {"4": {"nationality": "ITA", ...}, ...}}
    Anahtarlar satır numarası (string olarak gelebilir, int'e çevrilir).
    """
    sheet = body.get("sheet", "").strip()
    raw_updates = body.get("updates", {})

    if not sheet:
        raise HTTPException(status_code=422, detail="sheet alanı gerekli.")
    if not raw_updates:
        raise HTTPException(status_code=422, detail="updates alanı boş olamaz.")

    # Satır anahtarlarını int'e çevir
    updates: dict[int, dict] = {}
    for key, val in raw_updates.items():
        try:
            updates[int(key)] = val
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=422,
                detail=f"Geçersiz satır numarası: {key}",
            )

    s = _load_settings()
    try:
        if s.uses_google_sheets():
            from app import google_sheets as gs
            gs.write_identity(s, sheet, updates)
        else:
            xlsx_path = s.planning_path()
            if not xlsx_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Planlama dosyası bulunamadı: {xlsx_path}",
                )
            _backup_excel(xlsx_path)
            planning_write_identity(xlsx_path, sheet, updates)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kimlik yazılamadı: {e}")

    return {
        "success": True,
        "message": f"{len(updates)} satır güncellendi.",
        "rows_updated": list(updates.keys()),
    }


@app.post("/api/planning/write-operation")
def api_planning_write_operation(body: dict) -> dict:
    """Operasyon alanlarını (balon, pilot, otel, acente vb.) güncelle.

    body: {"sheet": "...", "lead_row": 4, "rows": [4,5,6], "fields": {"balloon": "BZR", ...}}
    """
    sheet = body.get("sheet", "").strip()
    lead_row = body.get("lead_row")
    rows = body.get("rows", [])
    fields = body.get("fields", {})

    if not sheet:
        raise HTTPException(status_code=422, detail="sheet alanı gerekli.")
    if lead_row is None:
        raise HTTPException(status_code=422, detail="lead_row alanı gerekli.")
    if not rows:
        raise HTTPException(status_code=422, detail="rows listesi boş olamaz.")
    if not fields:
        raise HTTPException(status_code=422, detail="fields alanı boş olamaz.")

    try:
        lead_row = int(lead_row)
        rows = [int(r) for r in rows]
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Geçersiz satır numarası.")

    s = _load_settings()
    try:
        if s.uses_google_sheets():
            from app import google_sheets as gs
            gs.write_operation_details(s, sheet, lead_row, rows, fields)
        else:
            xlsx_path = s.planning_path()
            if not xlsx_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Planlama dosyası bulunamadı: {xlsx_path}",
                )
            _backup_excel(xlsx_path)
            planning_write_operation_details(xlsx_path, sheet, lead_row, rows, fields)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Operasyon alanları yazılamadı: {e}")

    # Yeni otel/şoför/acente/pilot/geleceği yer değerlerini kalıcı listelere öğret
    if _remember_values(s, fields):
        settings_mod.save(s.normalized())

    return {
        "success": True,
        "message": f"Operasyon alanları güncellendi (lead_row={lead_row}).",
    }


# ═════════════════════════════════════════════════════════════════════
#  Pasaport (Passport)
# ═════════════════════════════════════════════════════════════════════

@app.post("/api/passport/upload")
async def api_passport_upload(
    files: list[UploadFile] = File(..., description="Pasaport/kimlik fotoğrafları"),
    sheet: Optional[str] = None,
    block_index: Optional[int] = None,
) -> dict:
    """Pasaport fotoğraflarını yükle ve MRZ ile işle.

    Claude modu açıksa Vision API ile MRZ okur; manual modda boş kayıt döndürür.
    Birden fazla dosya yüklenebilir (toplu işleme).
    """
    s = _load_settings()
    results: list[dict] = []
    # Duplicate tespiti için set (aynı yükleme içinde)
    seen_doc_numbers: set[str] = set()

    for upload_file in files:
        filename = upload_file.filename or "unknown"
        try:
            image_bytes = await upload_file.read()
        except Exception as e:
            results.append({
                "nationality": "", "sex": "", "name": "", "passport_no": "",
                "green": False, "flags": [Flag.UNREADABLE.value],
                "error": f"Dosya okunamadı: {e}", "source": filename,
            })
            continue

        if s.uses_claude():
            # Claude Vision ile MRZ okuma
            if not s.has_api_key():
                raise HTTPException(
                    status_code=400,
                    detail="Claude modu aktif ama API anahtarı ayarlanmamış.",
                )
            mt = media_type_for(Path(filename))
            record = process_image(
                image_bytes,
                source=filename,
                media_type=mt,
                model=s.model,
                seen_document_numbers=seen_doc_numbers,
            )
            field_data = record.to_fields()
            # Duplicate tespiti: başarılı okunan belge no'larını kaydet
            if record.mrz and record.mrz.document_number:
                seen_doc_numbers.add(record.mrz.document_number)
            results.append(field_data)
        else:
            # Manuel mod — boş kayıt döndür
            results.append({
                "nationality": "", "sex": "", "name": "", "passport_no": "",
                "green": False, "flags": [],
                "error": None, "source": filename,
            })

    return {
        "records": results,
        "count": len(results),
        "mode": "claude" if s.uses_claude() else "manual",
        "sheet": sheet,
        "block_index": block_index,
    }


@app.post("/api/passport/process-manual")
def api_passport_process_manual(body: dict) -> dict:
    """Manuel giriş için N adet boş pasaport kaydı üret.

    body: {"count": 3}
    """
    count = body.get("count", 1)
    try:
        count = int(count)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="count geçerli bir sayı olmalı.")

    if count < 1 or count > 50:
        raise HTTPException(status_code=422, detail="count 1–50 arasında olmalı.")

    records = [
        {
            "nationality": "", "sex": "", "name": "", "passport_no": "",
            "green": False, "flags": [],
            "error": None, "source": f"manual_{i + 1}",
        }
        for i in range(count)
    ]

    return {"records": records, "count": count, "mode": "manual"}


# ═════════════════════════════════════════════════════════════════════
#  Manifesto — API endpoint'leri
# ═════════════════════════════════════════════════════════════════════

@app.get("/api/manifest/preview")
def api_manifest_preview(
    sheet: str = Query(..., description="Planlama sayfa adı, ör. 22.06.2026"),
    balloon: str = Query(..., description="Balon kodu, ör. BZR"),
) -> dict:
    """Balon için manifesto satırlarını JSON olarak önizle."""
    s = _load_settings()
    try:
        xlsx_path = _resolve_planning_path(s)
        rows = build_rows(xlsx_path, sheet, balloon)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Manifesto önizleme hatası: {e}")

    return {
        "sheet": sheet,
        "balloon": balloon.upper(),
        "count": len(rows),
        "rows": [r.__dict__ for r in rows],
    }


@app.get("/api/manifest/export")
def api_manifest_export(
    sheet: str = Query(..., description="Planlama sayfa adı, ör. 22.06.2026"),
    balloon: str = Query(..., description="Balon kodu, ör. BZR"),
) -> FileResponse:
    """Balon için manifesto xlsx dosyasını üret ve indir."""
    s = _load_settings()
    out_dir = s.output_path()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        xlsx_path = _resolve_planning_path(s)
        path = export(xlsx_path, sheet, balloon, out_dir, s.template_path())
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Manifesto export hatası: {e}")

    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ═════════════════════════════════════════════════════════════════════
#  İstatistikler (Dashboard Stats)
# ═════════════════════════════════════════════════════════════════════

@app.get("/api/stats")
def api_stats() -> dict:
    """Dashboard istatistikleri: sayfa sayısı, çıkarım durumları, bugünün tarihi."""
    s = _load_settings()

    # Mevcut sayfa sayısı
    sheet_count = 0
    try:
        if s.uses_google_sheets():
            from app import google_sheets as gs
            sheet_count = len(gs.list_sheets(s))
        else:
            xlsx_path = s.planning_path()
            if xlsx_path.exists():
                sheet_count = len(planning_list_sheets(xlsx_path))
    except Exception:
        pass  # Sayfa sayısı alınamazsa 0 kal

    # DB'den çıkarım istatistikleri
    status_counts: dict[str, int] = {}
    total_extractions = 0
    try:
        conn = connect()
        try:
            cursor = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM passport_extraction GROUP BY status"
            )
            for row in cursor.fetchall():
                status_counts[row["status"]] = row["cnt"]
                total_extractions += row["cnt"]
        finally:
            conn.close()
    except Exception:
        pass  # DB erişilemezse boş kal

    return {
        "today": _dt.date.today().isoformat(),
        "sheet_count": sheet_count,
        "total_extractions": total_extractions,
        "extraction_by_status": status_counts,
        "data_source": s.data_source,
        "vision_mode": s.vision_mode,
    }


@app.get("/api/weather/status")
def api_weather_status() -> dict:
    """Hava durumu izleme: son durum + bugunun ucus risk karari."""
    s = _load_settings()
    if not s.weather_enabled:
        return weather_mod.cached_weather()
    try:
        return weather_mod.refresh_weather(s)
    except Exception as e:
        data = weather_mod.cached_weather()
        data["error"] = str(e)
        return data


@app.post("/api/weather/refresh")
def api_weather_refresh() -> dict:
    """Hava durumunu elle yenile ve son olcumu kaydet."""
    s = _load_settings()
    if not s.weather_enabled:
        raise HTTPException(status_code=400, detail="Weather monitor kapali.")
    try:
        return weather_mod.refresh_weather(s)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Hava durumu alinamadi: {e}")


# ═════════════════════════════════════════════════════════════════════
#  Eski (backward-compatible) endpoint'ler
# ═════════════════════════════════════════════════════════════════════

@app.get("/manifest/preview")
def manifest_preview(
    date: str = Query(..., description="Planlama sayfa adı, ör. 22.06.2026"),
    balloon: str = Query(..., description="Balon kodu, ör. BZR"),
) -> dict:
    """Eski endpoint — geriye dönük uyumluluk için korunuyor."""
    try:
        rows = build_rows(config.PLANNING_XLSX, date, balloon)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "date": date,
        "balloon": balloon.upper(),
        "count": len(rows),
        "rows": [r.__dict__ for r in rows],
    }


@app.get("/manifest/export")
def manifest_export(
    date: str = Query(..., description="Planlama sayfa adı, ör. 22.06.2026"),
    balloon: str = Query(..., description="Balon kodu, ör. BZR"),
) -> FileResponse:
    """Eski endpoint — geriye dönük uyumluluk için korunuyor."""
    out_dir = Path(tempfile.mkdtemp())
    try:
        path = export(config.PLANNING_XLSX, date, balloon, out_dir)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# --- Statik dosyalar: en son yükle (diğer endpoint'leri gölgelememesi için) ---
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
