"""OCR sağlayıcı arayüzü ve ortak doğrulama (docs/mimari-v2-ocr-sunucu.md §4.1, genişletilmiş).

Sahadan gelen malzeme tek tip değil: MRZ'li pasaport, kimlik ön yüzü (MRZ arkada),
acentenin basılı/el yazısı listeleri (işaretli satırlar uçuyor), WhatsApp rezervasyon
mesajı ekran görüntüsü. Bu yüzden sağlayıcı sözleşmesi ÇOK YOLCULU ve belge türlüdür:

    OcrResult.kind       : passport_mrz | id_card_mrz | id_front | printed_list |
                           handwritten_list | chat_message | other
    OcrResult.group      : görseldeki grup başlığı (tarih, otel, acente, pax, uyruk ipucu…)
    OcrResult.passengers : [{format, lines, fields, confidence, annotation, selected}, …]

`to_records()` her yolcuyu HER ZAMAN yerel MRZ parser + ICAO checksum'dan geçirir:
yeşil yalnız `MRZResult.checks_ok` ile mümkündür; alan-bazlı (MRZ'siz) okumalar her
zaman sarıdır (FREE_TEXT_UNVERIFIED) — operatör onaylar (brief §6, §8).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from app.mrz.parser import MRZResult
from app.validation.flags import Flag, ValidationOutcome

CONFIDENCE_LEVELS = ("green", "yellow", "red")
_CONFIDENCE_SCORE = {"green": 1.0, "yellow": 0.8, "red": 0.5}

KINDS = (
    "passport_mrz", "id_card_mrz", "id_front", "printed_list",
    "handwritten_list", "chat_message", "other",
)
# Belge türü → operatöre gösterilen kaynak rozeti
KIND_LABELS = {
    "passport_mrz": "Pasaport (MRZ)",
    "id_card_mrz": "Kimlik (MRZ)",
    "id_front": "Kimlik ön yüzü",
    "printed_list": "Basılı liste",
    "handwritten_list": "El yazısı liste",
    "chat_message": "Mesaj / rezervasyon",
    "other": "Diğer",
}

PASSENGER_FIELDS = (
    "first_name", "last_name", "nationality", "gender",
    "document_no", "document_type", "birth_date", "expiry_date",
)


@dataclass
class OcrResult:
    """Sağlayıcıdan dönen ham OCR sonucu. HTTP sözleşmesi (§4.2) ile aynı gövde."""

    status: str = "success"                 # "success" | "error"
    passenger: dict = field(default_factory=dict)   # tek yolcu (geriye uyumluluk)
    confidence: str = "red"                 # "green" | "yellow" | "red" (tek yolcu için)
    raw_text: str = ""                      # tek yolcunun MRZ satırları "\n" ile
    warnings: list[str] = field(default_factory=list)
    source: str = ""                        # "claude:claude-sonnet-5-5" | "google_vision" | ...
    usage: Optional[dict] = None
    error: Optional[str] = None
    # ── çok yolculu sözleşme ──
    kind: str = "other"                     # KINDS
    group: dict = field(default_factory=dict)       # date, hotel, agency, pax, nationality_hint, title, note
    passengers: list[dict] = field(default_factory=list)  # her biri: format, lines, fields, confidence, annotation, selected

    @classmethod
    def failure(cls, message: str, *, source: str = "") -> "OcrResult":
        return cls(status="error", confidence="red", source=source, error=message)

    @property
    def ok(self) -> bool:
        return self.status == "success" and not self.error

    @property
    def confidence_score(self) -> float:
        return _CONFIDENCE_SCORE.get(self.confidence, 0.5)

    def iter_passengers(self) -> list[dict]:
        """`passengers` doluysa onu, yoksa tek `passenger`/`raw_text`'i tek elemanlı liste olarak döner."""
        if self.passengers:
            return list(self.passengers)
        has_single = bool(self.passenger) or bool(self.raw_text)
        if not has_single:
            return []
        return [{
            "format": "",
            "lines": [ln for ln in (self.raw_text or "").split("\n") if ln.strip()],
            "fields": dict(self.passenger or {}),
            "confidence": self.confidence,
            "annotation": "",
            "selected": None,
        }]


@runtime_checkable
class OcrProvider(Protocol):
    name: str

    def read(self, image_bytes: bytes, media_type: str) -> OcrResult: ...


@dataclass
class OcrRecordOut:
    """`to_records()` çıktısı: tek yolcu için doğrulanmış sonuç + kaynak meta."""

    mrz: Optional[MRZResult]
    outcome: ValidationOutcome
    error: Optional[str]
    confidence_score: float
    route: str
    ai_model: Optional[str]
    kind: str = "other"
    annotation: str = ""
    selected: Optional[bool] = None
    group: dict = field(default_factory=dict)
    document_type: str = ""
    nationality_source: str = ""     # mrz | stated | header | document | pattern | list | model
    nationality_reason: str = ""

    def as_tuple(self):
        return (self.mrz, self.outcome, self.error, self.confidence_score, self.route, self.ai_model)


# ─── Yardımcılar ─────────────────────────────────────────────────────────────

def normalize_doc_no(value: Optional[str]) -> str:
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def _parse_iso_date(value) -> Optional[_dt.date]:
    if not value:
        return None
    try:
        return _dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _level(value) -> str:
    """Sağlayıcı güveni: 'green'/'yellow'/'red' ya da 0..1 sayı → seviye."""
    if isinstance(value, str) and value in CONFIDENCE_LEVELS:
        return value
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "red"
    if score >= 0.9:
        return "green"
    if score >= 0.7:
        return "yellow"
    return "red"


def parse_mrz_lines(lines: list[str]) -> Optional[MRZResult]:
    """Sağlayıcının verdiği MRZ satırlarını yerel parser ile (checksum dahil) okur."""
    from app.mrz.parser import parse

    cleaned = [str(ln).strip().upper() for ln in (lines or []) if str(ln).strip()]
    if len(cleaned) not in (2, 3):
        return None
    try:
        local = parse(cleaned)
    except Exception:
        return None
    return local if local.document_number else None


def parse_raw_mrz(raw_text: str) -> Optional[MRZResult]:
    """Ham OCR metninden MRZ satırlarını bulup yerel parser ile okur."""
    if not raw_text:
        return None
    from app.vision.ocr import mrz_lines_from_text

    try:
        fmt, lines = mrz_lines_from_text(raw_text)
    except Exception:
        return None
    if fmt == "NONE" or not lines:
        return None
    return parse_mrz_lines(lines)


def verify_against_local_mrz(mrz: MRZResult, raw_text: str, *, server_document_no: str) -> None:
    """Sağlayıcı alanlarını ham metindeki MRZ ile KODDA doğrular (geriye uyumlu yardımcı)."""
    local = parse_raw_mrz(raw_text)
    if local is None:
        return
    _merge_local_into(mrz, local, server_document_no=server_document_no)


def _merge_local_into(mrz: MRZResult, local: MRZResult, *, server_document_no: str) -> None:
    checks = dict(local.checks)
    server_doc = normalize_doc_no(server_document_no)
    checks["server_document_match"] = (
        server_doc == normalize_doc_no(local.document_number) if server_doc else True
    )
    mrz.checks = checks
    mrz.raw_lines = list(local.raw_lines)
    mrz.format = local.format
    if not mrz.document_number:
        mrz.document_number = local.document_number
    if not mrz.nationality:
        mrz.nationality = local.nationality
        mrz.issuing_country = local.issuing_country
    if mrz.sex not in ("M", "F") and local.sex in ("M", "F"):
        mrz.sex = local.sex
    if mrz.expiry_date is None:
        mrz.expiry_date = local.expiry_date
    if mrz.birth_date is None:
        mrz.birth_date = local.birth_date


def _fields_to_mrz(fields: dict, *, kind: str, group: dict) -> MRZResult:
    """MRZ'siz okuma (liste, kimlik ön yüzü, mesaj): alanlardan checks={} ile MRZResult."""
    nat = str(fields.get("nationality") or group.get("nationality_hint") or "").strip().upper()[:3]
    gender = str(fields.get("gender") or "").strip().upper()[:1]
    return MRZResult(
        format={"id_front": "ID_FRONT", "printed_list": "LIST", "handwritten_list": "LIST",
                "chat_message": "MESSAGE"}.get(kind, "FIELDS"),
        document_type=str(fields.get("document_type") or "")[:2] or "ID",
        issuing_country=nat,
        nationality=nat,
        document_number=str(fields.get("document_no") or "").strip().upper(),
        sex=gender if gender in ("M", "F") else "X",
        surname=str(fields.get("last_name") or "").strip().upper(),
        given_names=str(fields.get("first_name") or "").strip().upper(),
        birth_date=_parse_iso_date(fields.get("birth_date")),
        expiry_date=_parse_iso_date(fields.get("expiry_date")),
        checks={},
        raw_lines=[],
    )


def _passenger_to_record(p: dict, *, kind: str, group: dict, route: str, ai_model: Optional[str]) -> OcrRecordOut:
    fields = p.get("fields") if isinstance(p.get("fields"), dict) else {}
    lines = p.get("lines") if isinstance(p.get("lines"), list) else []
    level = _level(p.get("confidence", "red"))
    annotation = str(p.get("annotation") or "").strip()
    selected = p.get("selected")
    selected = selected if isinstance(selected, bool) else None
    document_type = str(fields.get("document_type") or "").strip().upper()

    local = parse_mrz_lines(lines)
    has_fields = any(fields.get(k) for k in ("document_no", "first_name", "last_name"))

    if local is None and not has_fields:
        return OcrRecordOut(
            None, ValidationOutcome(flags=[Flag.UNREADABLE]), "MRZ bulunamadı/okunamadı",
            0.0, route, ai_model, kind=kind, annotation=annotation, selected=selected, group=group,
        )

    flags: list[Flag] = []
    if local is not None:
        # MRZ okundu → checks gerçek. Alanlar varsa belge no ile çapraz kontrol.
        if has_fields:
            mrz = _fields_to_mrz(fields, kind=kind, group=group)
            mrz.format = local.format
            _merge_local_into(mrz, local, server_document_no=str(fields.get("document_no") or ""))
        else:
            mrz = local
        if level != "green":
            flags.append(Flag.LOW_CONFIDENCE)
    else:
        mrz = _fields_to_mrz(fields, kind=kind, group=group)   # checks={} → FREE_TEXT_UNVERIFIED (validate_mrz)
        if level != "green":
            flags.append(Flag.LOW_CONFIDENCE)

    stated_nat = str(fields.get("nationality") or "").strip()
    if local is not None:
        nat_source = "mrz"
    elif stated_nat:
        nat_source = "stated"
    elif mrz.nationality:
        nat_source = "header"        # _fields_to_mrz grup ipucunu uyguladı
    else:
        nat_source = ""
    return OcrRecordOut(
        mrz, ValidationOutcome(flags=flags), None, _CONFIDENCE_SCORE[level], route, ai_model,
        kind=kind, annotation=annotation, selected=selected, group=group, document_type=document_type,
        nationality_source=nat_source,
    )


def to_records(result: OcrResult, *, provider_name: str = "") -> list[OcrRecordOut]:
    """OcrResult → doğrulanmış kayıt listesi (her yolcu için bir OcrRecordOut).

    Sağlayıcıdan bağımsız değişmezler:
    1. `checks` boşsa asla yeşil (validate_mrz → FREE_TEXT_UNVERIFIED).
    2. MRZ satırı ile `fields.document_no` çelişirse → CHECKSUM_FAIL.
    3. expired / duplicate yerel hesaplanır (validate_mrz, çağıranda).
    4. Listelerde her satır ayrı kayıt; `annotation` (✓, SI, sıra no, fosfor…) yorumlanmadan taşınır.
    """
    route = provider_name or result.source or "unknown"
    ai_model = result.source or None
    if not result.ok:
        return [OcrRecordOut(
            None, ValidationOutcome(flags=[Flag.UNREADABLE]), result.error or "OCR başarısız.",
            0.0, route, ai_model, kind=result.kind or "other",
        )]

    kind = result.kind if result.kind in KINDS else "other"
    group = dict(result.group or {})

    # Sunucu sözleşmesindeki uyarılar tek-yolcu sonuçlara uygulanır
    extra_flags: list[Flag] = []
    for w in result.warnings or []:
        w = str(w).lower()
        if "expired" in w:
            extra_flags.append(Flag.EXPIRED)
        elif "checksum" in w:
            extra_flags.append(Flag.CHECKSUM_FAIL)

    passengers = result.iter_passengers()
    if not passengers:
        return [OcrRecordOut(
            None, ValidationOutcome(flags=[Flag.UNREADABLE]), "MRZ bulunamadı/okunamadı",
            0.0, route, ai_model, kind=kind, group=group,
        )]

    records = []
    for p in passengers:
        rec = _passenger_to_record(p, kind=kind, group=group, route=route, ai_model=ai_model)
        if rec.mrz is not None and not result.passengers:
            for f in extra_flags:
                rec.outcome.add(f)
            # Tek-yolcu modunda sunucu ham metin verdiyse MRZ'yi oradan da dene (eski davranış)
            if not rec.mrz.checks and result.raw_text:
                verify_against_local_mrz(rec.mrz, result.raw_text,
                                         server_document_no=str((result.passenger or {}).get("document_no") or ""))
        records.append(rec)
    return records


def to_mrz(
    result: OcrResult,
    *,
    provider_name: str = "",
) -> tuple[Optional[MRZResult], ValidationOutcome, Optional[str], float, str, Optional[str]]:
    """Geriye uyumlu tek-yolcu görünüm: ilk kaydın (mrz, outcome, error, score, route, model) demeti."""
    return to_records(result, provider_name=provider_name)[0].as_tuple()
