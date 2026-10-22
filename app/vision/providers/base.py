"""OCR sağlayıcı arayüzü ve ortak doğrulama (docs/mimari-v2-ocr-sunucu.md §4.1).

Sözleşme: sağlayıcı (`OcrProvider.read`) görseli okur ve `OcrResult` döner.
`to_mrz()` bu sonucu HER ZAMAN yerel MRZ parser + ICAO 9303 checksum'dan geçirir;
sağlayıcının `confidence` değeri yalnız sarı/kırmızı ayrımına etki eder, yeşil
ancak `MRZResult.checks_ok` ile mümkündür (brief §6).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from app.mrz.parser import MRZResult
from app.validation.flags import Flag, ValidationOutcome

CONFIDENCE_LEVELS = ("green", "yellow", "red")
_CONFIDENCE_SCORE = {"green": 1.0, "yellow": 0.8, "red": 0.5}


@dataclass
class OcrResult:
    """Sağlayıcıdan dönen ham OCR sonucu. HTTP sözleşmesi (§4.2) ile aynı gövde."""

    status: str = "success"                 # "success" | "error"
    passenger: dict = field(default_factory=dict)   # first_name, last_name, nationality, gender,
                                                     # document_no, birth_date, expiry_date (ISO | None)
    confidence: str = "red"                 # "green" | "yellow" | "red"
    raw_text: str = ""                      # MRZ satırları "\n" ile; checksum BURADAN hesaplanır
    warnings: list[str] = field(default_factory=list)   # "expired", "checksum", "no_mrz", ...
    source: str = ""                        # "claude:claude-sonnet-5-5" | "google_vision" | ...
    usage: Optional[dict] = None            # {"input_tokens", "output_tokens", "usd", ...} isteğe bağlı
    error: Optional[str] = None             # status == "error" iken operatöre gösterilecek metin

    @classmethod
    def failure(cls, message: str, *, source: str = "") -> "OcrResult":
        return cls(status="error", confidence="red", source=source, error=message)

    @property
    def ok(self) -> bool:
        return self.status == "success" and not self.error

    @property
    def confidence_score(self) -> float:
        return _CONFIDENCE_SCORE.get(self.confidence, 0.5)


@runtime_checkable
class OcrProvider(Protocol):
    name: str

    def read(self, image_bytes: bytes, media_type: str) -> OcrResult: ...


# ─── Yerel doğrulama yardımcıları ───────────────────────────────────────────

def normalize_doc_no(value: Optional[str]) -> str:
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def _parse_iso_date(value) -> Optional[_dt.date]:
    if not value:
        return None
    try:
        return _dt.date.fromisoformat(str(value))
    except ValueError:
        return None


def parse_raw_mrz(raw_text: str) -> Optional[MRZResult]:
    """Ham OCR metninden MRZ satırlarını bulup yerel parser ile (checksum dahil) okur."""
    if not raw_text:
        return None
    from app.vision.ocr import mrz_lines_from_text
    from app.mrz.parser import parse

    try:
        fmt, lines = mrz_lines_from_text(raw_text)
        if fmt == "NONE" or not lines:
            return None
        local = parse(lines)
    except Exception:
        return None
    return local if local.document_number else None


def verify_against_local_mrz(mrz: MRZResult, raw_text: str, *, server_document_no: str) -> None:
    """Sağlayıcı alanlarını ham metindeki MRZ ile KODDA doğrular (brief §6).

    - MRZ parse edilirse `mrz.checks` yerel check digit sonuçlarıyla dolar; ek olarak
      `server_document_match` (sağlayıcının belge no'su == MRZ belge no).
    - MRZ bulunamazsa `checks` boş kalır → `validate_mrz` FREE_TEXT_UNVERIFIED verir (sarı).
    """
    local = parse_raw_mrz(raw_text)
    if local is None:
        return

    checks = dict(local.checks)
    server_doc = normalize_doc_no(server_document_no)
    checks["server_document_match"] = (
        server_doc == normalize_doc_no(local.document_number) if server_doc else True
    )
    mrz.checks = checks
    mrz.raw_lines = list(local.raw_lines)

    # Sağlayıcının boş bıraktığı alanları doğrulanmış MRZ'den tamamla
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


def to_mrz(
    result: OcrResult,
    *,
    provider_name: str = "",
) -> tuple[Optional[MRZResult], ValidationOutcome, Optional[str], float, str, Optional[str]]:
    """OcrResult → (mrz, outcome, error_msg, confidence_score, route, ai_model).

    Sağlayıcıdan bağımsız değişmezler:
    1. `checks` boşsa asla yeşil (validate_mrz → FREE_TEXT_UNVERIFIED).
    2. `raw_text` MRZ'si ile `passenger.document_no` çelişirse → CHECKSUM_FAIL.
    3. expired / duplicate yerel hesaplanır (validate_mrz, çağıranda).
    """
    route = provider_name or result.source or "unknown"
    if not result.ok:
        return (
            None,
            ValidationOutcome(flags=[Flag.UNREADABLE]),
            result.error or "OCR başarısız.",
            0.0,
            route,
            result.source or None,
        )

    p = result.passenger or {}
    raw_text = result.raw_text or ""
    has_fields = any(p.get(k) for k in ("document_no", "first_name", "last_name"))

    # Sağlayıcı alan vermedi (örn. claude_direct yalnız MRZ satırı döner) → doğrudan yerel parse
    if not has_fields:
        local = parse_raw_mrz(raw_text)
        if local is None:
            return (
                None,
                ValidationOutcome(flags=[Flag.UNREADABLE]),
                "MRZ bulunamadı/okunamadı",
                0.0,
                route,
                result.source or None,
            )
        flags = [] if result.confidence == "green" else [Flag.LOW_CONFIDENCE]
        return local, ValidationOutcome(flags=flags), None, result.confidence_score, route, result.source or None

    name_first = str(p.get("first_name") or "")
    name_last = str(p.get("last_name") or "")
    mrz = MRZResult(
        format="SERVER_OCR",
        document_type="ID",
        issuing_country=str(p.get("nationality") or "")[:3],
        nationality=str(p.get("nationality") or "")[:3],
        document_number=str(p.get("document_no") or ""),
        sex=str(p.get("gender") or "X") or "X",
        surname=name_last,
        given_names=name_first,
        birth_date=_parse_iso_date(p.get("birth_date")),
        expiry_date=_parse_iso_date(p.get("expiry_date")),
        checks={},
        raw_lines=[raw_text] if raw_text else [],
    )
    verify_against_local_mrz(mrz, raw_text, server_document_no=str(p.get("document_no") or ""))

    flags: list[Flag] = []
    if result.confidence != "green":
        flags.append(Flag.LOW_CONFIDENCE)
    for w in result.warnings or []:
        w = str(w).lower()
        if "expired" in w:
            flags.append(Flag.EXPIRED)
        elif "checksum" in w:
            flags.append(Flag.CHECKSUM_FAIL)

    return mrz, ValidationOutcome(flags=flags), None, result.confidence_score, route, result.source or None
