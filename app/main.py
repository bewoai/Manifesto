"""FastAPI uygulaması — Web UI için genişletilmiş API yüzeyi.

Deterministik çekirdek (health + manifesto) + planlama CRUD + pasaport
yükleme + ayarlar yönetimi + istatistik dashboard endpoint'leri.
"""
from __future__ import annotations

import tempfile
import datetime as _dt
import os
import threading
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app import settings as settings_mod
from app import weather as weather_mod
from app import auth as auth_mod
from app import audit as audit_mod
from app.db import connect, init_db
from app.excel_store import (
    WorkbookConflictError,
    WorkbookLockedError,
    atomic_update,
    list_backups,
    restore_backup,
    workbook_revision,
)
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
    reorder_reservation as planning_reorder_reservation,
    delete_passenger_from_reservation as planning_delete_passenger,
    resize_reservation as planning_resize_reservation,
    write_identity as planning_write_identity,
    write_operation_details as planning_write_operation_details,
)
from app.manifest.writer import ManifestRow, build_rows, export, write_manifest
from app.vision.extractor import PassportRecord, process_image
from app.validation.flags import Flag, ValidationOutcome
from app.passport_store import (
    ROOT as PASSPORT_IMAGE_ROOT,
    cleanup_day as cleanup_passport_day,
    cleanup_stale,
    save_image,
)
from app.readiness import check_blocks, check_workbook
from app.reports import (
    driver_rows,
    driver_summary,
    export_driver_reports,
    export_summary,
    zip_outputs,
)
from app.version import APP_VERSION
from app import updater as updater_mod

app = FastAPI(title="İrtifa Uçuş Sistemi", version=APP_VERSION)

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
    if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/auth/"):
        if not auth_mod.setup_required():
            user = auth_mod.user_for_session(
                request.cookies.get(auth_mod.SESSION_COOKIE)
            )
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Oturum açmanız gerekiyor."},
                )
            request.state.user = user
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
    weather_mod.normalize_stored_weather_texts()
    weather_mod.start_weather_worker()
    cleanup_stale()


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


def _sync_sqlite(sheet: str) -> None:
    """Excel'deki güncellemelerin ardından SQLite veritabanını günceller."""
    try:
        from app.manifest.importer import import_excel_to_sqlite
        import_excel_to_sqlite(sheet_name=sheet)
    except Exception as e:
        print(f"Warning: Failed to sync Excel sheet '{sheet}' to SQLite: {e}")



def _mask_api_key(key: str) -> str:
    """API anahtarının sadece son 4 karakterini göster, geri kalanını maskele."""
    if not key or len(key) <= 4:
        return key
    return "*" * (len(key) - 4) + key[-4:]


def _actor(request: Request | None) -> str:
    user = getattr(getattr(request, "state", None), "user", None)
    return user["username"] if user else "system"


def _require_admin(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if not user or user["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="Bu işlem için yönetici yetkisi gerekli.",
        )
    return user


def _atomic_error(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkbookConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, WorkbookLockedError):
        return HTTPException(status_code=423, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


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
    return {"success": True, "message": "İrtifa kapatılıyor."}


# ═════════════════════════════════════════════════════════════════════
#  Kimlik doğrulama
# ═════════════════════════════════════════════════════════════════════

@app.get("/api/auth/status")
def api_auth_status(request: Request) -> dict:
    s = _load_settings()
    user = auth_mod.user_for_session(
        request.cookies.get(auth_mod.SESSION_COOKIE)
    )
    return {
        "setup_required": auth_mod.setup_required(),
        "authenticated": bool(user),
        "user": user,
        "is_setup_complete": s.is_setup_complete,
    }


@app.post("/api/auth/setup")
def api_auth_setup(body: dict, response: Response) -> dict:
    try:
        user, recovery_code = auth_mod.create_initial_admin(
            body.get("username", ""),
            body.get("display_name", ""),
            body.get("password", ""),
        )
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    token = auth_mod.create_session(user["id"])
    response.set_cookie(
        auth_mod.SESSION_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        max_age=auth_mod.SESSION_DAYS * 86400,
    )
    audit_mod.record("initial_admin_created", actor=user["username"])
    return {"user": user, "recovery_code": recovery_code}


@app.post("/api/auth/login")
def api_auth_login(body: dict, response: Response) -> dict:
    user = auth_mod.authenticate(
        body.get("username", ""), body.get("password", "")
    )
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Kullanıcı adı veya parola hatalı.",
        )
    token = auth_mod.create_session(user["id"])
    response.set_cookie(
        auth_mod.SESSION_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        max_age=auth_mod.SESSION_DAYS * 86400,
    )
    audit_mod.record("login", actor=user["username"])
    return {"user": user}


@app.post("/api/auth/logout")
def api_auth_logout(request: Request, response: Response) -> dict:
    auth_mod.delete_session(request.cookies.get(auth_mod.SESSION_COOKIE))
    response.delete_cookie(auth_mod.SESSION_COOKIE)
    return {"success": True}


@app.get("/api/app/status")
def api_app_status() -> dict:
    s = _load_settings()
    has_license = bool(s.irtifa_license_key and s.irtifa_license_key.strip())
    return {
        "licensed": has_license,
        "skipped": s.irtifa_license_skipped,
        "is_setup_complete": s.is_setup_complete,
        "version": APP_VERSION,
    }


@app.post("/api/app/skip_license")
def api_app_skip_license(request: Request) -> dict:
    _require_admin(request)
    s = _load_settings()
    s.irtifa_license_skipped = True
    settings_mod.save(s)
    return {"success": True}


@app.get("/api/auth/me")
def api_auth_me(request: Request) -> dict:
    user = auth_mod.user_for_session(request.cookies.get(auth_mod.SESSION_COOKIE))
    return {"user": user, "setup_required": auth_mod.setup_required()}


@app.post("/api/auth/recover")
def api_auth_recover(body: dict) -> dict:
    try:
        auth_mod.reset_admin_with_recovery(
            body.get("recovery_code", ""), body.get("new_password", "")
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    audit_mod.record("admin_password_recovered")
    return {"success": True, "message": "Yönetici parolası sıfırlandı."}


@app.get("/api/admin/users")
def api_admin_users(request: Request) -> dict:
    _require_admin(request)
    return {"users": auth_mod.list_users()}


@app.post("/api/admin/users")
def api_admin_create_user(request: Request, body: dict) -> dict:
    _require_admin(request)
    try:
        user = auth_mod.create_user(
            body.get("username", ""),
            body.get("display_name", ""),
            body.get("password", ""),
            body.get("role", "operator"),
        )
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    audit_mod.record("user_created", actor=_actor(request), detail={"username": user["username"]})
    return {"user": user}


@app.get("/api/admin/audit")
def api_admin_audit(
    request: Request,
    limit: int = 200,
    actor: str = "",
    action: str = "",
) -> dict:
    _require_admin(request)
    return {"entries": audit_mod.list_entries(limit=limit, actor=actor, action=action)}


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
    data["irtifa_license_key"] = _mask_api_key(s.irtifa_license_key)
    data["google_credentials_json"] = (
        "Korumalı depoda kayıtlı" if s.google_credentials_json else ""
    )
    # Türetilmiş bilgileri de ekle
    data["_derived"] = {
        "planning_path": str(s.planning_path()),
        "template_path": str(s.template_path()),
        "output_path": str(s.output_path()),
        "uses_claude": s.uses_claude(),
        "uses_google_vision": s.uses_google_vision(),
        "uses_automatic_vision": s.uses_automatic_vision(),
        "has_api_key": s.has_api_key(),
        "uses_google_sheets": s.uses_google_sheets(),
        "google_is_configured": s.google_is_configured(),
    }
    return data


@app.put("/api/settings")
def update_settings(body: dict, request: Request) -> dict:
    """Ayarları güncelle, doğrula ve kaydet. Güncel halini döndür."""
    _require_admin(request)
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
            if key == "irtifa_license_key" and body[key] and "*" in body[key]:
                continue
            if key == "google_credentials_json" and body[key] == "Korumalı depoda kayıtlı":
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
    data["irtifa_license_key"] = _mask_api_key(updated.irtifa_license_key)
    data["google_credentials_json"] = (
        "Korumalı depoda kayıtlı" if updated.google_credentials_json else ""
    )
    data["_derived"] = {
        "planning_path": str(updated.planning_path()),
        "template_path": str(updated.template_path()),
        "output_path": str(updated.output_path()),
        "uses_claude": updated.uses_claude(),
        "uses_google_vision": updated.uses_google_vision(),
        "uses_automatic_vision": updated.uses_automatic_vision(),
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


class GenerateMonthlyRequest(BaseModel):
    year: int
    month: int


@app.post("/api/planning/generate-monthly")
def api_generate_monthly(req: GenerateMonthlyRequest) -> dict[str, Any]:
    """Native dialog ile yeni bir aylık plan dosyası oluştur."""
    import tkinter as tk
    from tkinter import filedialog
    from app.flight_plan_generator import generate_monthly_flight_plan, MONTHS_TR
    import os

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    m_tr = MONTHS_TR[req.month].capitalize() if 1 <= req.month <= 12 else ""
    default_name = f"Ucus_Plani_{req.year}_{req.month:02d}_{m_tr}.xlsx"

    save_path = filedialog.asksaveasfilename(
        title="Aylık Uçuş Planı Kaydet",
        initialfile=default_name,
        defaultextension=".xlsx",
        filetypes=[("Excel Dosyaları", "*.xlsx")]
    )
    root.destroy()

    if not save_path:
        return {"success": False, "message": "İptal edildi"}

    try:
        generate_monthly_flight_plan(req.year, req.month, save_path)
        # Yeni planı ayarlara kaydet (otomatik geçiş)
        s = _load_settings()
        s.planning_xlsx = str(save_path)
        settings_mod.save(s)
        # Sadece Windows'ta geçerli:
        if os.name == 'nt':
            os.startfile(save_path)
        return {"success": True, "path": save_path, "message": "Uçuş planı oluşturuldu ve ayarlandı."}
    except Exception as e:
        raise HTTPException(500, f"Oluşturma hatası: {e}")

@app.post("/api/planning/import-existing")
def api_import_existing(request: Request) -> dict[str, Any]:
    """Native dialog ile var olan bir Excel dosyasını seç ve ayarla."""
    _require_admin(request)
    import tkinter as tk
    from tkinter import filedialog
    import os

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    open_path = filedialog.askopenfilename(
        title="Mevcut Uçuş Planını Seç",
        defaultextension=".xlsx",
        filetypes=[("Excel Dosyaları", "*.xlsx")]
    )
    root.destroy()

    if not open_path:
        return {"success": False, "message": "İptal edildi"}

    try:
        s = _load_settings()
        s.planning_xlsx = str(open_path)
        settings_mod.save(s)
        return {"success": True, "path": open_path, "message": "Mevcut uçuş planı bağlandı."}
    except Exception as e:
        raise HTTPException(500, f"İçe aktarma hatası: {e}")


class PlanningImportBody(BaseModel):
    sheet: Optional[str] = None


@app.post("/api/planning/import")
def api_planning_import(request: Request, body: Optional[PlanningImportBody] = None) -> dict[str, Any]:
    """Excel planlama dosyasındaki verileri SQLite'a aktarır."""
    _require_admin(request)
    sheet_name = body.sheet if body else None
    from app.manifest.importer import import_excel_to_sqlite
    try:
        stats = import_excel_to_sqlite(sheet_name=sheet_name)
        return stats
    except Exception as e:
        raise HTTPException(500, f"Veri aktarım hatası: {e}")

@app.post("/api/settings/import-directory")
def api_import_directory(request: Request) -> dict[str, Any]:
    """Native dialog ile klasör seç."""
    _require_admin(request)
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    open_path = filedialog.askdirectory(title="Çıktı Klasörünü Seç")
    root.destroy()

    if not open_path:
        return {"success": False, "message": "İptal edildi"}

    try:
        s = _load_settings()
        s.output_dir = str(open_path)
        settings_mod.save(s)
        return {"success": True, "path": open_path, "message": "Çıktı klasörü ayarlandı."}
    except Exception as e:
        raise HTTPException(500, f"Klasör seçme hatası: {e}")


# ═════════════════════════════════════════════════════════════════════
#  Planlama: Blok Ekle / Sil
# ═════════════════════════════════════════════════════════════════════


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


@app.post("/api/lists/scan")
def api_lists_scan() -> dict:
    """Planlama Excel'indeki geçmiş günleri tarayıp öneri listelerini doldur."""
    s = _load_settings()
    if s.uses_google_sheets():
        raise HTTPException(
            status_code=400,
            detail="Otomatik liste tarama şu an yalnızca Excel modunda destekleniyor.",
        )

    xlsx_path = s.planning_path()
    if not xlsx_path.exists():
        raise HTTPException(status_code=404, detail=f"Planlama dosyası bulunamadı: {xlsx_path}")

    added = 0
    try:
        sheets = planning_list_sheets(xlsx_path)
        for sheet in sheets:
            try:
                blocks = read_blocks(xlsx_path, sheet)
            except Exception:
                continue
            for block in blocks:
                fields = {
                    "hotel": block.hotel,
                    "driver": block.driver,
                    "agency": block.agency,
                    "pilot": block.pilot,
                    "coming_place": block.coming_place,
                    "reserved_by": block.reserved_by,
                }
                before = _lists_payload(s)
                if _remember_values(s, fields):
                    after = _lists_payload(s)
                    added += sum(
                        max(
                            0,
                            len(after["options"].get(cat, []))
                            - len(before["options"].get(cat, [])),
                        )
                        for cat in LIST_CATEGORIES
                    )
                balloon = str(block.balloon or "").strip().upper()
                if balloon and balloon != "BALON" and balloon not in {c.upper() for c in s.balloon_codes}:
                    s.balloon_codes.append(balloon)
                    added += 1
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Listeler taranamadı: {exc}")

    s = s.normalized()
    settings_mod.save(s)
    payload = _lists_payload(s)
    payload["added"] = added
    return payload


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
    xlsx_path = _resolve_planning_path(s)
    
    from app.manifest.importer import sheet_name_to_iso, load_blocks_from_sqlite
    iso_date = sheet_name_to_iso(sheet)
    blocks = None
    loaded_from_db = False
    
    if iso_date:
        try:
            conn = connect()
            flight = conn.execute("SELECT id FROM flights WHERE flight_date = ?", (iso_date,)).fetchone()
            if flight:
                res_count = conn.execute("SELECT COUNT(*) FROM reservations WHERE flight_id = ?", (flight["id"],)).fetchone()[0]
                if res_count > 0:
                    blocks = load_blocks_from_sqlite(flight["id"], conn)
                    loaded_from_db = True
            conn.close()
        except Exception as e:
            print(f"Warning: Failed to load from SQLite: {e}")
            
    if not loaded_from_db:
        try:
            blocks = read_blocks(xlsx_path, sheet)
            if iso_date:
                def run_bg():
                    try:
                        from app.manifest.importer import import_excel_to_sqlite
                        import_excel_to_sqlite(sheet_name=sheet)
                    except Exception as e:
                        print(f"Background import failed for {sheet}: {e}")
                threading.Thread(target=run_bg, daemon=True).start()
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Sayfa yüklenemedi: {e}")

    try:
        revision = workbook_revision(xlsx_path)
    except Exception:
        revision = "unknown"

    # Balon kodları: Settings rosterü + sayfada görülenlerin birleşimi
    seen_codes = {b.balloon for b in blocks if b.balloon}
    balloon_codes = list(s.balloon_codes)
    for code in sorted(seen_codes):
        if code not in balloon_codes:
            balloon_codes.append(code)

    load = planning_balloon_load(blocks)
    readiness = check_blocks(
        blocks,
        balloon_capacity=s.balloon_capacity,
    )

    return {
        "sheet": sheet,
        "blocks": [_block_to_dict(b) for b in blocks],
        "balloon_codes": balloon_codes,
        "balloon_load": load,
        "capacity": s.balloon_capacity,
        "total_blocks": len(blocks),
        "workbook_revision": revision,
        "readiness": readiness,
    }



@app.post("/api/planning/create-day")
def api_planning_create_day(body: dict, request: Request) -> dict:
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
            _, revision, backup = atomic_update(
                xlsx_path,
                expected_revision=body.get("expected_revision"),
                reason="create_day",
                mutator=lambda temp: planning_create_day_sheet(temp, new_sheet, source_sheet),
            )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (WorkbookConflictError, WorkbookLockedError) as e:
        raise _atomic_error(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sayfa oluşturulamadı: {e}")

    audit_mod.record("day_created", actor=_actor(request), sheet=new_sheet)
    if not s.uses_google_sheets():
        _sync_sqlite(new_sheet)
    return {
        "success": True,
        "message": f"'{new_sheet}' sayfası oluşturuldu.",
        "workbook_revision": revision if not s.uses_google_sheets() else None,
        "backup": backup.name if not s.uses_google_sheets() else None,
    }


@app.post("/api/planning/create-block")
def api_planning_create_block(body: dict, request: Request) -> dict:
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
    requested_balloon = str(body.get("requested_balloon", "")).strip().upper()
    allow_overflow = bool(body.get("allow_overflow"))
    if overflow and not (allow_overflow and requested_balloon in s.balloon_codes):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "capacity_confirmation_required",
                "message": "Hiçbir balonda grubun tamamına yer yok.",
                "balloon_load": load,
                "capacity": s.balloon_capacity,
                "balloon_codes": s.balloon_codes,
            },
        )
    if overflow:
        balloon = requested_balloon
    pilot = planning_pilot_for_balloon(rows, balloon)

    try:
        result, revision, backup = atomic_update(
            xlsx_path,
            expected_revision=body.get("expected_revision"),
            reason="create_reservation",
            mutator=lambda temp: planning_create_reservation(
                temp, sheet, pax=pax, balloon=balloon, pilot=pilot, fields=lead_fields
            ),
        )
    except (WorkbookConflictError, WorkbookLockedError) as e:
        raise _atomic_error(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rezervasyon yazılamadı: {e}")

    # Yeni otel/acente/şoför değerlerini kalıcı listelere öğret
    if _remember_values(s, lead_fields):
        settings_mod.save(s.normalized())

    new_load = dict(load)
    new_load[balloon] = new_load.get(balloon, 0) + pax
    audit_mod.record(
        "reservation_created",
        actor=_actor(request),
        sheet=sheet,
        reservation_row=result["lead_row"],
        detail={"pax": pax, "balloon": balloon, "overflow": overflow},
    )
    _sync_sqlite(sheet)
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
        "workbook_revision": revision,
        "backup": backup.name,
    }


@app.post("/api/planning/reorder-block")
def api_planning_reorder_block(body: dict, request: Request) -> dict:
    """Bir rezervasyon bloğunu (source_rows) hedef satırın (target_row) üstüne taşır."""
    sheet = body.get("sheet", "").strip()
    source_rows = body.get("source_rows", [])
    target_row = body.get("target_row")
    if not sheet:
        raise HTTPException(status_code=422, detail="sheet alanı gerekli.")
    if not source_rows or target_row is None:
        raise HTTPException(status_code=422, detail="source_rows ve target_row gerekli.")
    
    s = _load_settings()
    if s.uses_google_sheets():
        raise HTTPException(status_code=400, detail="Yeniden sıralama şu an yalnızca Excel modunda.")
    xlsx_path = s.planning_path()
    if not xlsx_path.exists():
        raise HTTPException(status_code=404, detail="Planlama dosyası bulunamadı.")
    
    try:
        _, revision, backup = atomic_update(
            xlsx_path,
            expected_revision=body.get("expected_revision"),
            reason="reorder_reservation",
            mutator=lambda temp: planning_reorder_reservation(temp, sheet, source_rows, target_row),
        )
    except (WorkbookConflictError, WorkbookLockedError) as e:
        raise _atomic_error(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sıralama hatası: {e}")
    
    _sync_sqlite(sheet)
    return {"success": True, "workbook_revision": revision, "backup": backup.name}


@app.post("/api/planning/delete-block")
def api_planning_delete_block(body: dict, request: Request) -> dict:
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
        _, revision, backup = atomic_update(
            xlsx_path,
            expected_revision=body.get("expected_revision"),
            reason="delete_reservation",
            mutator=lambda temp: planning_delete_reservation(temp, sheet, rows),
        )
    except (WorkbookConflictError, WorkbookLockedError) as e:
        raise _atomic_error(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rezervasyon silinemedi: {e}")
    audit_mod.record(
        "reservation_deleted",
        actor=_actor(request),
        sheet=sheet,
        reservation_row=min(rows),
        detail={"row_count": len(rows)},
    )
    _sync_sqlite(sheet)
    return {
        "success": True,
        "message": f"{len(rows)} satırlık rezervasyon silindi.",
        "workbook_revision": revision,
        "backup": backup.name,
    }


@app.post("/api/planning/delete-passenger")
def api_planning_delete_passenger(body: dict, request: Request) -> dict:
    """Bir rezervasyon bloğundan tek yolcu sil."""
    sheet = body.get("sheet", "").strip()
    lead_row = body.get("lead_row")
    rows = body.get("rows", [])
    target_row = body.get("row")
    if not sheet:
        raise HTTPException(status_code=422, detail="sheet alanı gerekli.")
    if lead_row is None or target_row is None:
        raise HTTPException(status_code=422, detail="lead_row ve row alanları gerekli.")
    if not rows:
        raise HTTPException(status_code=422, detail="rows listesi boş olamaz.")
    try:
        lead_row = int(lead_row)
        target_row = int(target_row)
        rows = [int(r) for r in rows]
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Geçersiz satır numarası.")

    s = _load_settings()
    if s.uses_google_sheets():
        raise HTTPException(status_code=400, detail="Yolcu silme şu an yalnızca Excel modunda.")
    xlsx_path = s.planning_path()
    if not xlsx_path.exists():
        raise HTTPException(status_code=404, detail=f"Planlama dosyası bulunamadı: {xlsx_path}")
    try:
        result, revision, backup = atomic_update(
            xlsx_path,
            expected_revision=body.get("expected_revision"),
            reason="delete_passenger",
            mutator=lambda temp: planning_delete_passenger(
                temp,
                sheet,
                lead_row=lead_row,
                rows=rows,
                target_row=target_row,
            ),
        )
    except (WorkbookConflictError, WorkbookLockedError) as e:
        raise _atomic_error(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Yolcu silinemedi: {e}")
    audit_mod.record(
        "passenger_deleted",
        actor=_actor(request),
        sheet=sheet,
        reservation_row=lead_row,
        detail={"target_row": target_row},
    )
    _sync_sqlite(sheet)
    return {
        "success": True,
        "message": "Yolcu rezervasyondan silindi.",
        "workbook_revision": revision,
        "backup": backup.name,
        **result,
    }


@app.post("/api/planning/write-identity")
def api_planning_write_identity(body: dict, request: Request) -> dict:
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
            _, revision, backup = atomic_update(
                xlsx_path,
                expected_revision=body.get("expected_revision"),
                reason="write_identity",
                mutator=lambda temp: planning_write_identity(temp, sheet, updates),
            )
    except HTTPException:
        raise
    except (WorkbookConflictError, WorkbookLockedError) as e:
        raise _atomic_error(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kimlik yazılamadı: {e}")

    audit_mod.record(
        "identity_written",
        actor=_actor(request),
        sheet=sheet,
        detail={"rows": list(updates.keys()), "count": len(updates)},
    )
    if not s.uses_google_sheets():
        _sync_sqlite(sheet)
    return {
        "success": True,
        "message": f"{len(updates)} satır güncellendi.",
        "rows_updated": list(updates.keys()),
        "workbook_revision": revision if not s.uses_google_sheets() else None,
        "backup": backup.name if not s.uses_google_sheets() else None,
    }


@app.post("/api/planning/write-operation")
def api_planning_write_operation(body: dict, request: Request) -> dict:
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
            def mutate(temp: Path):
                target_rows = rows
                if "pax" in fields:
                    try:
                        new_pax = int(fields["pax"])
                    except (TypeError, ValueError):
                        raise ValueError("PAX tam sayı olmalı.")
                    target_rows = planning_resize_reservation(
                        temp,
                        sheet,
                        lead_row=lead_row,
                        rows=rows,
                        new_pax=new_pax,
                        allow_data_loss=bool(body.get("allow_data_loss")),
                    )
                operation_fields = {k: v for k, v in fields.items() if k != "pax"}
                if operation_fields:
                    planning_write_operation_details(
                        temp, sheet, lead_row, target_rows, operation_fields
                    )
                return target_rows

            new_rows, revision, backup = atomic_update(
                xlsx_path,
                expected_revision=body.get("expected_revision"),
                reason="write_operation",
                mutator=mutate,
            )
    except HTTPException:
        raise
    except (WorkbookConflictError, WorkbookLockedError) as e:
        raise _atomic_error(e)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Operasyon alanları yazılamadı: {e}")

    # Yeni otel/şoför/acente/pilot/geleceği yer değerlerini kalıcı listelere öğret
    if _remember_values(s, fields):
        settings_mod.save(s.normalized())

    audit_mod.record(
        "operation_updated",
        actor=_actor(request),
        sheet=sheet,
        reservation_row=lead_row,
        detail={"fields": sorted(fields.keys())},
    )
    if not s.uses_google_sheets():
        _sync_sqlite(sheet)
    return {
        "success": True,
        "message": f"Operasyon alanları güncellendi (lead_row={lead_row}).",
        "rows": new_rows if not s.uses_google_sheets() else rows,
        "workbook_revision": revision if not s.uses_google_sheets() else None,
        "backup": backup.name if not s.uses_google_sheets() else None,
    }


def _clean_identities(raw: list) -> list[dict]:
    identities: list[dict] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        identity = {
            "nationality": str(item.get("nationality", "")).strip().upper(),
            "sex": str(item.get("sex", "")).strip().upper(),
            "name": str(item.get("name", "")).strip().upper(),
            "passport_no": str(item.get("passport_no", "")).strip().upper(),
        }
        if identity["name"] or identity["passport_no"]:
            identity["extraction_id"] = item.get("extraction_id")
            identities.append(identity)
    return identities


def _is_operational_ocr_error(error: object) -> bool:
    text = str(error or "").casefold()
    markers = (
        "lisans",
        "ulaşılamıyor",
        "kullanım kotası",
        "sunucu adresi",
        "cihaz kimliği",
        "geçersiz yanıt",
        "geçici bir hata",
        "en fazla 10 mb",
        "dosya boyutu",
    )
    return any(marker in text for marker in markers)


_ALLOWED_PASSPORT_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp"}
_PASSPORT_MEDIA_TYPES_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_MAX_PASSPORT_IMAGE_BYTES = 10 * 1024 * 1024


def _passport_content_type(filename: str, content_type: str) -> str:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if media_type in {"", "application/octet-stream"}:
        return _PASSPORT_MEDIA_TYPES_BY_SUFFIX.get(Path(filename).suffix.lower(), media_type)
    return media_type


def _validate_passport_upload(image_bytes: bytes, content_type: str) -> None:
    if content_type not in _ALLOWED_PASSPORT_MEDIA_TYPES:
        raise ValueError("Yalnız JPG, PNG ve WEBP görseller desteklenir.")
    if not image_bytes:
        raise ValueError("Görsel dosyası boş.")
    if len(image_bytes) > _MAX_PASSPORT_IMAGE_BYTES:
        raise ValueError("Görsel en fazla 10 MB olabilir.")


def _mark_extractions_approved(identities: list[dict], sheet: str, rows: list[int]) -> None:
    conn = connect()
    try:
        for identity, row in zip(identities, rows):
            extraction_id = identity.get("extraction_id")
            if extraction_id:
                conn.execute(
                    """
                    UPDATE passport_extraction
                    SET status = 'approved', planning_date = ?, planning_row = ?
                    WHERE id = ?
                    """,
                    (sheet, row, extraction_id),
                )
        conn.commit()
    finally:
        conn.close()


@app.post("/api/planning/create-with-identities")
def api_create_with_identities(body: dict, request: Request) -> dict:
    """Atomically create a reservation and write its approved identities."""
    sheet = str(body.get("sheet", "")).strip()
    identities = _clean_identities(body.get("identities", []))
    try:
        pax = int(body.get("pax") or len(identities))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="PAX tam sayı olmalı.")
    if not sheet or not (1 <= pax <= config.MAX_PAX):
        raise HTTPException(status_code=422, detail="Gün ve 1-28 arası PAX gerekli.")
    if len(identities) > pax:
        raise HTTPException(status_code=422, detail="Onaylı kimlik sayısı PAX değerini aşamaz.")

    s = _load_settings()
    if s.uses_google_sheets():
        raise HTTPException(status_code=400, detail="Bu akış Excel modunda kullanılabilir.")
    path = s.planning_path()
    fields = {
        key: str(body.get(key, "")).strip()
        for key in ("agency", "hotel", "pickup", "room", "reserved_by", "note", "driver")
        if body.get(key) not in (None, "")
    }

    current_blocks = read_blocks(path, sheet)
    current_load = planning_balloon_load(current_blocks)
    suggested, overflow = planning_assign_balloon(
        current_load, pax, s.balloon_codes, s.balloon_capacity
    )
    requested = str(body.get("requested_balloon", "")).strip().upper()
    if overflow and not (body.get("allow_overflow") and requested in s.balloon_codes):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "capacity_confirmation_required",
                "message": "Hiçbir balonda grubun tamamına yer yok.",
                "balloon_load": current_load,
                "capacity": s.balloon_capacity,
                "balloon_codes": s.balloon_codes,
            },
        )
    balloon = requested if overflow else suggested

    def mutate(temp: Path) -> dict:
        rows = read_rows(temp, sheet)
        pilot = planning_pilot_for_balloon(rows, balloon)
        result = planning_create_reservation(
            temp, sheet, pax=pax, balloon=balloon, pilot=pilot, fields=fields
        )
        updates = {
            row: {key: value for key, value in identity.items() if key != "extraction_id"}
            for row, identity in zip(result["rows"], identities)
        }
        if updates:
            planning_write_identity(temp, sheet, updates)
        result["pilot"] = pilot
        return result

    try:
        result, revision, backup = atomic_update(
            path,
            expected_revision=body.get("expected_revision"),
            reason="create_with_identities",
            mutator=mutate,
        )
    except (WorkbookConflictError, WorkbookLockedError) as exc:
        raise _atomic_error(exc)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Rezervasyon oluşturulamadı: {exc}")

    _mark_extractions_approved(identities, sheet, result["rows"])
    audit_mod.record(
        "reservation_with_identities_created",
        actor=_actor(request),
        sheet=sheet,
        reservation_row=result["lead_row"],
        detail={"pax": pax, "identity_count": len(identities), "balloon": balloon},
    )
    if not s.uses_google_sheets():
        _sync_sqlite(sheet)
    return {
        "success": True,
        **result,
        "overflow": overflow,
        "capacity": s.balloon_capacity,
        "workbook_revision": revision,
        "backup": backup.name,
    }


@app.post("/api/planning/append-identities")
def api_append_identities(body: dict, request: Request) -> dict:
    """Write approved identities only into empty rows of an existing block."""
    sheet = str(body.get("sheet", "")).strip()
    lead_row = int(body.get("lead_row") or 0)
    identities = _clean_identities(body.get("identities", []))
    if not sheet or not lead_row or not identities:
        raise HTTPException(status_code=422, detail="Gün, rezervasyon ve kimlikler gerekli.")
    s = _load_settings()
    if s.uses_google_sheets():
        raise HTTPException(status_code=400, detail="Bu akış Excel modunda kullanılabilir.")
    path = s.planning_path()

    def mutate(temp: Path) -> dict:
        block = next(
            (item for item in read_blocks(temp, sheet) if item.lead_row == lead_row),
            None,
        )
        if not block:
            raise ValueError("Rezervasyon bulunamadı.")
        empty_rows = [
            passenger.row
            for passenger in block.passengers
            if not passenger.name and not passenger.passport_no
        ]
        if len(identities) > len(empty_rows):
            raise ValueError(
                f"Rezervasyonda {len(empty_rows)} boş yolcu satırı var; "
                f"{len(identities)} kimlik eklenemez."
            )
        target_rows = empty_rows[:len(identities)]
        updates = {
            row: {key: value for key, value in identity.items() if key != "extraction_id"}
            for row, identity in zip(target_rows, identities)
        }
        planning_write_identity(temp, sheet, updates)
        return {"rows": target_rows, "empty_after": len(empty_rows) - len(target_rows)}

    try:
        result, revision, backup = atomic_update(
            path,
            expected_revision=body.get("expected_revision"),
            reason="append_identities",
            mutator=mutate,
        )
    except (WorkbookConflictError, WorkbookLockedError) as exc:
        raise _atomic_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Kimlikler eklenemedi: {exc}")

    _mark_extractions_approved(identities, sheet, result["rows"])
    audit_mod.record(
        "identities_appended",
        actor=_actor(request),
        sheet=sheet,
        reservation_row=lead_row,
        detail={"count": len(identities), "rows": result["rows"]},
    )
    if not s.uses_google_sheets():
        _sync_sqlite(sheet)
    return {
        "success": True,
        **result,
        "workbook_revision": revision,
        "backup": backup.name,
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

    for file_index, upload_file in enumerate(files):
        filename = upload_file.filename or "unknown"
        try:
            image_bytes = await upload_file.read()
            content_type = _passport_content_type(filename, upload_file.content_type or "")
            _validate_passport_upload(image_bytes, content_type)
            staged_path = save_image(image_bytes, filename)
        except Exception as e:
            results.append({
                "nationality": "", "sex": "", "name": "", "passport_no": "",
                "green": False, "flags": [Flag.UNREADABLE.value],
                "error": f"Dosya okunamadı: {e}", "source": filename,
            })
            continue

        if s.uses_automatic_vision():
            # Claude Vision ile MRZ okuma
            if s.uses_claude() and not s.has_api_key():
                raise HTTPException(
                    status_code=400,
                    detail="Claude modu aktif ama API anahtarı ayarlanmamış.",
                )
            try:
                records = process_image(
                    image_bytes,
                    source=filename,
                    media_type=content_type,
                    model=s.model,
                    provider=s.vision_mode,
                    settings=s,
                    seen_document_numbers=seen_doc_numbers,
                )
            except Exception as e:
                import traceback
                traceback.print_exc()
                results.append({
                    "nationality": "", "sex": "", "name": "", "passport_no": "",
                    "green": False, "flags": [Flag.UNREADABLE.value],
                    "error": f"İşleme hatası: {str(e)}", "source": filename,
                    "_source_file_name": filename,
                    "_source_file_index": file_index
                })
                continue
                
            for record in records:
                field_data = record.to_fields()
                # Aynı dosya adına sahip görselleri de güvenle ayırabilmek için
                # yükleme sırasını ve görünen adı birlikte döndür.
                field_data["_source_file_name"] = filename
                field_data["_source_file_index"] = file_index
                if not _is_operational_ocr_error(field_data.get("error")):
                    conn = connect()
                    try:
                        cursor = conn.execute(
                            """
                            INSERT INTO passport_extraction(
                                source_media_id, mrz_format, nationality, sex, name,
                                document_number, birth_date, expiry_date, checks_ok, flags, status,
                                confidence_score, processing_route, ai_model_used, fallback_reason, requires_manual_review
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
                            """,
                            (
                                str(staged_path),
                                record.mrz.format if record.mrz else None,
                                field_data.get("nationality"),
                                field_data.get("sex"),
                                field_data.get("name"),
                                field_data.get("passport_no"),
                                field_data.get("birth_date"),
                                field_data.get("expiry_date"),
                                int(bool(record.is_green)),
                                ",".join(field_data.get("flags", [])),
                                field_data.get("confidence_score", 1.0),
                                field_data.get("processing_route", "irtifa_server"),
                                field_data.get("ai_model_used"),
                                field_data.get("fallback_reason"),
                                int(field_data.get("requires_manual_review", False)),
                            ),
                        )
                        conn.commit()
                        field_data["extraction_id"] = cursor.lastrowid
                    finally:
                        conn.close()
                else:
                    try:
                        staged_path.unlink()
                    except OSError:
                        pass
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
        "mode": s.vision_mode,
        "sheet": sheet,
        "block_index": block_index,
    }


@app.post("/api/passport/retry-ocr")
@app.post("/api/passport/retry-claude", include_in_schema=False)
async def api_passport_retry_ocr(
    file: UploadFile = File(...),
) -> dict:
    s = _load_settings()
    image_bytes = await file.read()
    filename = file.filename or "passport.jpg"
    content_type = _passport_content_type(filename, file.content_type or "")
    try:
        _validate_passport_upload(image_bytes, content_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    staged_path = save_image(image_bytes, filename)
    records = process_image(
        image_bytes,
        source=filename,
        media_type=content_type,
        provider=settings_mod.VISION_MODE_IRTIFA_SERVER,
        settings=s,
        model=s.model,
    )
    if not records:
         raise HTTPException(status_code=400, detail="Hiçbir şey okunamadı.")
    
    # Retry endpoint genelde tek görsel tek kişi beklenir ama process_image liste döner. 
    # Frontend ilk kaydı alır genelde. (Veya hepsini liste dönebiliriz, orijinal kod record = process_image(...) diyordu ama array döndüğünü unuttuğu için patlayabilirdi. Onu da düzelttik.)
    record = records[0]
    fields = record.to_fields()
    if _is_operational_ocr_error(fields.get("error")):
        try:
            staged_path.unlink()
        except OSError:
            pass
        raise HTTPException(status_code=503, detail=fields["error"])
    conn = connect()
    try:
        cursor = conn.execute(
            """
            INSERT INTO passport_extraction(
                source_media_id, mrz_format, nationality, sex, name,
                document_number, birth_date, expiry_date, checks_ok, flags, status,
                confidence_score, processing_route, ai_model_used, fallback_reason, requires_manual_review
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
            """,
            (
                str(staged_path),
                record.mrz.format if record.mrz else None,
                fields.get("nationality"),
                fields.get("sex"),
                fields.get("name"),
                fields.get("passport_no"),
                fields.get("birth_date"),
                fields.get("expiry_date"),
                int(bool(record.is_green)),
                ",".join(fields.get("flags", [])),
                fields.get("confidence_score", 1.0),
                fields.get("processing_route", "google_vision"),
                fields.get("ai_model_used"),
                fields.get("fallback_reason"),
                int(fields.get("requires_manual_review", False)),
            ),
        )
        conn.commit()
        fields["extraction_id"] = cursor.lastrowid
    finally:
        conn.close()
    return fields


@app.get("/api/passport/manual-review")
def api_passport_manual_review() -> dict:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT id, created_at, source_media_id, mrz_format, nationality, sex, name,
                   document_number, flags, status, confidence_score, processing_route,
                   ai_model_used, fallback_reason, manual_review_reason
            FROM passport_extraction
            WHERE requires_manual_review = 1 AND status = 'pending'
            ORDER BY created_at ASC
            """
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()

@app.get("/api/passport/image/{id}")
def api_passport_get_image(id: int):
    conn = connect()
    try:
        row = conn.execute("SELECT source_media_id FROM passport_extraction WHERE id = ?", (id,)).fetchone()
        if not row or not row["source_media_id"]:
            raise HTTPException(404, "Image not found")
        path = Path(row["source_media_id"]).resolve()
        root = PASSPORT_IMAGE_ROOT.resolve()
        if path != root and root not in path.parents:
            raise HTTPException(403, "Görsel yolu geçersiz.")
        if not path.is_file():
            raise HTTPException(404, "File not found on disk")
        return FileResponse(path)
    finally:
        conn.close()

class ResolveManualReviewRequest(BaseModel):
    id: int
    action: str  # 'approve' veya 'reject'
    corrected_data: Optional[dict] = None

@app.post("/api/passport/manual-review/resolve")
def api_passport_manual_review_resolve(req: ResolveManualReviewRequest, request: Request) -> dict:
    if req.action not in {"approve", "reject"}:
        raise HTTPException(status_code=422, detail="Geçersiz manuel kontrol işlemi.")

    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT id, status, requires_manual_review, source_media_id
            FROM passport_extraction
            WHERE id = ?
            """,
            (req.id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Kontrol kaydı bulunamadı.")
        if row["status"] != "pending" or not row["requires_manual_review"]:
            raise HTTPException(status_code=409, detail="Bu kayıt daha önce işlenmiş.")

        if req.action == "approve":
            d = req.corrected_data or {}
            nationality = str(d.get("nationality", "")).strip().upper()
            sex = str(d.get("sex", "")).strip().upper()
            name = str(d.get("name", "")).strip().upper()
            document_number = str(d.get("document_number", "")).strip().upper()
            if len(nationality) != 3 or not nationality.isalpha():
                raise HTTPException(status_code=422, detail="Uyruk üç harfli kod olmalı.")
            if sex not in {"M", "F", "X"}:
                raise HTTPException(status_code=422, detail="Cinsiyet M, F veya X olmalı.")
            if not name or not document_number:
                raise HTTPException(
                    status_code=422,
                    detail="İsim ve pasaport/kimlik numarası zorunlu.",
                )
            duplicate = conn.execute(
                """
                SELECT id FROM passport_extraction
                WHERE document_number = ? AND id != ? AND status != 'rejected'
                LIMIT 1
                """,
                (document_number, req.id),
            ).fetchone()
            if duplicate:
                raise HTTPException(
                    status_code=409,
                    detail="Bu pasaport/kimlik numarası başka bir kayıtta bulunuyor.",
                )
            conn.execute(
                """
                UPDATE passport_extraction
                SET nationality = ?, sex = ?, name = ?, document_number = ?, 
                    requires_manual_review = 0, checks_ok = 1,
                    flags = '', manual_review_reason = 'operator_approved'
                WHERE id = ?
                """,
                (nationality, sex, name, document_number, req.id),
            )
            result = {
                "extraction_id": req.id,
                "nationality": nationality,
                "sex": sex,
                "name": name,
                "passport_no": document_number,
                "green": True,
                "flags": [],
                "requires_manual_review": False,
                "manual_reviewed": True,
                "source": (
                    Path(row["source_media_id"]).name
                    if row["source_media_id"]
                    else ""
                ),
            }
        elif req.action == "reject":
            conn.execute(
                "UPDATE passport_extraction SET status = 'rejected', requires_manual_review = 0 WHERE id = ?",
                (req.id,),
            )
            result = None
        conn.commit()
    finally:
        conn.close()

    audit_mod.record(
        "manual_review_approved" if req.action == "approve" else "manual_review_rejected",
        actor=_actor(request),
        detail={"extraction_id": req.id},
    )
    return {"success": True, "record": result}


@app.post("/api/passport/cleanup")
def api_passport_cleanup(request: Request, body: dict) -> dict:
    requested_day = str(body.get("day") or "").strip()
    sheet = str(body.get("sheet") or "").strip()
    if not requested_day and sheet:
        try:
            requested_day = _dt.datetime.strptime(
                sheet, "%d.%m.%Y"
            ).date().isoformat()
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="Seçilen sayfa adı tarih biçiminde değil. Günlük temizlik yapılamadı.",
            )
    result = cleanup_passport_day(requested_day or None)
    conn = connect()
    try:
        conn.execute(
            "DELETE FROM passport_extraction WHERE date(created_at) = date(?)",
            (result["day"],),
        )
        conn.commit()
    finally:
        conn.close()
    audit_mod.record(
        "passport_temp_data_cleaned",
        actor=_actor(request),
        sheet=sheet or None,
        detail=result,
    )
    return {"success": True, **result}


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
    request: Request,
    sheet: str = Query(..., description="Planlama sayfa adı, ör. 22.06.2026"),
    balloon: str = Query(..., description="Balon kodu, ör. BZR"),
    override_reason: str = "",
) -> FileResponse:
    """Balon için manifesto xlsx dosyasını üret ve indir."""
    s = _load_settings()
    out_dir = s.output_path()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        xlsx_path = _resolve_planning_path(s)
        readiness = check_workbook(
            xlsx_path, sheet, balloon_capacity=s.balloon_capacity
        )
        if readiness["issue_count"] and not override_reason.strip():
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "readiness_override_required",
                    "message": "Uçuşa hazır kontrolünde eksikler var.",
                    "readiness": readiness,
                },
            )
        path = export(xlsx_path, sheet, balloon, out_dir, s.template_path())
    except HTTPException:
        raise
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Manifesto export hatası: {e}")

    audit_mod.record(
        "manifest_exported",
        actor=_actor(request),
        sheet=sheet,
        detail={
            "balloon": balloon.upper(),
            "override_reason": override_reason.strip() or None,
            "issue_count": readiness["issue_count"],
        },
    )
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/readiness")
def api_readiness(sheet: str) -> dict:
    s = _load_settings()
    path = _resolve_planning_path(s)
    return check_workbook(path, sheet, balloon_capacity=s.balloon_capacity)


@app.get("/api/reports/drivers/preview")
def api_driver_report_preview(sheet: str) -> dict:
    s = _load_settings()
    path = _resolve_planning_path(s)
    blocks = read_blocks(path, sheet)
    grouped = driver_rows(blocks)
    return {
        "drivers": [
            {"driver": driver, "count": len(rows), "rows": rows}
            for driver, rows in grouped.items()
        ],
        "summary": driver_summary(blocks),
    }


@app.post("/api/reports/drivers/export")
def api_driver_report_export(request: Request, body: dict) -> FileResponse:
    sheet = str(body.get("sheet", "")).strip()
    driver = str(body.get("driver", "")).strip()
    if not sheet:
        raise HTTPException(status_code=422, detail="Gün seçimi gerekli.")
    s = _load_settings()
    path = _resolve_planning_path(s)
    out_dir = s.output_path() / _safe_output_name(sheet) / "Sofor_Listeleri"
    paths = export_driver_reports(path, sheet, out_dir, selected_driver=driver)
    if not paths:
        raise HTTPException(status_code=404, detail="Şoför listesi oluşturulamadı.")
    summary_paths = export_summary(
        path,
        sheet,
        out_dir,
        overrides=body.get("summary_overrides") or {},
    )
    zip_path = out_dir / (
        f"Sofor_{_safe_output_name(driver)}.zip" if driver else "Tum_Sofor_Listeleri.zip"
    )
    zip_outputs(paths + summary_paths, zip_path)
    audit_mod.record(
        "driver_reports_exported",
        actor=_actor(request),
        sheet=sheet,
        detail={"driver": driver or "all"},
    )
    return FileResponse(zip_path, filename=zip_path.name, media_type="application/zip")


def _safe_output_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)


@app.post("/api/reports/all")
def api_all_outputs(request: Request, body: dict) -> FileResponse:
    sheet = str(body.get("sheet", "")).strip()
    reason = str(body.get("override_reason", "")).strip()
    if not sheet:
        raise HTTPException(status_code=422, detail="Gün seçimi gerekli.")
    s = _load_settings()
    planning_path = _resolve_planning_path(s)
    readiness = check_workbook(
        planning_path, sheet, balloon_capacity=s.balloon_capacity
    )
    if readiness["issue_count"] and not reason:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "readiness_override_required",
                "message": "Eksiklerle devam etmek için gerekçe gerekli.",
                "readiness": readiness,
            },
        )
    out_dir = s.output_path() / _safe_output_name(sheet)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = export_driver_reports(planning_path, sheet, out_dir / "Sofor_Listeleri")
    outputs += export_summary(
        planning_path,
        sheet,
        out_dir / "Sofor_Listeleri",
        overrides=body.get("summary_overrides") or {},
    )
    blocks = read_blocks(planning_path, sheet)
    balloons = sorted({block.balloon for block in blocks if block.balloon})
    manifest_dir = out_dir / "Manifestolar"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    for balloon in balloons:
        outputs.append(export(planning_path, sheet, balloon, manifest_dir, s.template_path()))
    zip_path = out_dir / f"Irtifa_{_safe_output_name(sheet)}_Tum_Ciktilar.zip"
    zip_outputs(outputs, zip_path)
    audit_mod.record(
        "all_outputs_exported",
        actor=_actor(request),
        sheet=sheet,
        detail={"override_reason": reason or None, "files": len(outputs)},
    )
    return FileResponse(zip_path, filename=zip_path.name, media_type="application/zip")


@app.get("/api/admin/backups")
def api_admin_backups(request: Request) -> dict:
    _require_admin(request)
    s = _load_settings()
    return {"backups": list_backups(s.planning_path())}


@app.post("/api/admin/backups/restore")
def api_admin_restore_backup(request: Request, body: dict) -> dict:
    _require_admin(request)
    s = _load_settings()
    try:
        revision, safety_backup = restore_backup(
            s.planning_path(), str(body.get("name", ""))
        )
    except (FileNotFoundError, WorkbookLockedError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    audit_mod.record(
        "backup_restored",
        actor=_actor(request),
        detail={"name": body.get("name"), "safety_backup": safety_backup.name},
    )
    return {"success": True, "workbook_revision": revision}


@app.post("/api/settings/test")
def api_settings_test(body: dict, request: Request) -> dict:
    _require_admin(request)
    target = body.get("target")
    s = _load_settings()
    try:
        if target == "planning":
            path = s.planning_path()
            if not path.exists():
                raise FileNotFoundError(path)
            sheets = planning_list_sheets(path)
            return {"success": True, "message": f"{len(sheets)} uçuş günü okundu."}
        if target == "irtifa_server":
            import requests
            # Eğer ön yüzden güncel değerler gönderildiyse (kaydedilmemiş form state), onları kullan:
            test_url = body.get("irtifa_server_url") or s.irtifa_server_url
            test_key = body.get("irtifa_license_key") or s.irtifa_license_key
            test_device = s.irtifa_device_id

            if not test_key:
                raise ValueError("Lisans anahtarı gerekli. Lütfen ayarlara lisansınızı girin.")
            if not test_url:
                raise ValueError("Sunucu adresi gerekli.")

            endpoint = test_url.rstrip("/") + "/ocr/passport"
            headers = {
                "x-license-key": str(test_key),
                "x-device-id": str(test_device),
            }
            files = {"file": ("test.jpg", b"1", "image/jpeg")}
            try:
                resp = requests.post(endpoint, headers=headers, files=files, timeout=15)
                if resp.status_code in {401, 403}:
                    raise ValueError("Lisans anahtarı geçersiz.")
                if resp.status_code == 404:
                    raise ValueError("Sunucu adresi geçersiz veya endpoint bulunamadı.")
                if resp.status_code in {502, 503, 504}:
                    raise ValueError(f"OCR sunucusu geçici olarak hizmet veremiyor (Hata: {resp.status_code}).")
                # Treat 500 as connection successful, because sending b"1" dummy image
                # likely causes an internal server error on the vision API parser.
                if resp.status_code not in {200, 400, 413, 415, 422, 429, 500}:
                    raise ValueError(
                        f"OCR sunucusu beklenmeyen yanıt verdi ({resp.status_code})."
                    )
            except requests.exceptions.RequestException:
                raise ValueError("Sunucuya ulaşılamıyor. URL'yi kontrol edin.")
            return {"success": True, "message": "İrtifa OCR Servisi ile bağlantı başarılı."}
        raise ValueError("Geçersiz bağlantı testi.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Bağlantı kurulamadı: {exc}")


@app.get("/api/update/status")
def api_update_status(request: Request) -> dict:
    _require_admin(request)
    s = _load_settings()
    try:
        return updater_mod.check(s.update_manifest_url)
    except Exception as exc:
        return {
            "configured": bool(s.update_manifest_url),
            "current_version": APP_VERSION,
            "available": False,
            "error": str(exc),
        }


@app.post("/api/update/download")
def api_update_download(request: Request, body: dict) -> dict:
    _require_admin(request)
    s = _load_settings()
    status = updater_mod.check(s.update_manifest_url)
    if not status.get("available"):
        raise HTTPException(status_code=409, detail="Yeni sürüm bulunamadı.")
    try:
        path = updater_mod.stage(status["manifest"], s.update_public_key)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Güncelleme doğrulanamadı: {exc}")
    audit_mod.record(
        "update_staged",
        actor=_actor(request),
        detail={"version": status.get("latest_version")},
    )
    return {"success": True, "path": str(path), "version": status.get("latest_version")}


@app.post("/api/update/install")
def api_update_install(request: Request) -> dict:
    _require_admin(request)
    if not updater_mod.launch_pending_install():
        raise HTTPException(status_code=409, detail="Kurulmaya hazır güncelleme bulunamadı.")
    audit_mod.record("update_install_started", actor=_actor(request))
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return {"success": True, "message": "Güncelleme uygulanıyor."}


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
    """Hava durumu izleme: son durum + bugünün uçuş risk kararı."""
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
    """Hava durumunu elle yenile ve son ölçümü kaydet."""
    s = _load_settings()
    if not s.weather_enabled:
        raise HTTPException(status_code=400, detail="Hava durumu takibi kapalı.")
    try:
        return weather_mod.refresh_weather(s)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Hava durumu alınamadı: {e}")


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
