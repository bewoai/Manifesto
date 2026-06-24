"""Vision katmanı — pasaport/kimlik fotoğrafından MRZ okuma (Claude).

Akış: görsel -> Claude Vision (yalnızca MRZ satırlarını JSON döndürür)
      -> app.mrz.parser (TD3/TD1 + ICAO 9303 checksum, DETERMİNİSTİK)
      -> app.validation.flags (yeşil/sarı).

Model SADECE OCR eder; checksum ve alan doğrulaması kodda yapılır. Böylece
model hatası checksum'a takılır (brief §6).
"""
from __future__ import annotations

import base64
import datetime as _dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app import settings as settings_mod
from app.mrz.parser import MRZResult, parse_td1, parse_td3
from app.validation.flags import Flag, ValidationOutcome, validate_mrz
from app.vision.ocr import extract_with_google_vision

# Claude'a hem MRZ hem de serbest metinden tüm yolcuları çıkarttırıyoruz.
SYSTEM_PROMPT = (
    "You are an expert OCR and data extraction system for passports, IDs, and booking lists. "
    "Your task is to identify and extract ALL passenger identities from the provided image. "
    "The image may be a passport photo, a WhatsApp message, a booking screenshot, or an Excel list. "
    "For EACH passenger found, extract their details into an array. "
    "If the passenger has a Machine Readable Zone (MRZ) (2 lines of 44 chars for TD3, or 3 lines of 30 chars for TD1 with '<' filler), "
    "extract the EXACT MRZ lines into `mrz_lines` and set `format` to TD3 or TD1. "
    "If the passenger is found in free text, a list, or APIS string (no MRZ), set `format` to NONE and `mrz_lines` to an empty array, "
    "but extract their `nationality` (3-letter ISO code if possible), `sex` (M, F, or X), `name` (full name, uppercase), and `passport_no` (or ID number) directly from the text. "
    "If the gender/sex is not explicitly stated but can be inferred from title (MR/MRS/MS), infer it. "
    "Ensure `name` does NOT include the passport number or dates. "
    "Output ONLY the requested JSON."
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "passengers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["TD3", "TD1", "TR_ID_FRONT", "NONE"]},
                    "lines": {"type": "array", "items": {"type": "string"}},
                    "fields": {
                        "type": "object",
                        "properties": {
                            "nationality": {"type": "string"},
                            "sex": {"type": "string", "enum": ["M", "F", "X", ""]},
                            "name": {"type": "string"},
                            "passport_no": {"type": "string"}
                        },
                        "additionalProperties": True
                    }
                },
                "required": ["format", "lines"]
            }
        }
    },
    "required": ["passengers"],
    "additionalProperties": False,
}

_MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif",
}


def media_type_for(path: Path) -> str:
    return _MEDIA_TYPES.get(Path(path).suffix.lower(), "image/jpeg")


def _valid_tc(n: str) -> bool:
    """T.C. Kimlik No checksum doğrulaması (10. ve 11. hane)."""
    if len(n) != 11 or not n.isdigit() or n[0] == "0":
        return False
    d = [int(c) for c in n]
    if ((sum(d[0:9:2]) * 7) - sum(d[1:8:2])) % 10 != d[9]:
        return False
    return sum(d[:10]) % 10 == d[10]


def _tr_tc_no_from_line1(line1: str) -> Optional[str]:
    """Türk kimliği (TD1): TC Kimlik No 1. satırın opsiyonel alanındadır (11 hane, harfsiz).
    Belge SERİ no (harfli) yerine bunu kullanırız. Geçerli TC bulunamazsa None."""
    optional = line1[15:30] if len(line1) >= 30 else line1[15:]
    digits = re.sub(r"\D", "", optional)
    for m in re.finditer(r"\d{11}", digits):
        if _valid_tc(m.group()):
            return m.group()
    return digits if len(digits) == 11 else None


@dataclass
class PassportRecord:
    """Kontrol ekranı + planlamaya yazma için tek pasaportun tüm çıktısı."""
    source: str                       # görsel dosya yolu / id
    mrz: Optional[MRZResult]
    outcome: ValidationOutcome
    error: Optional[str] = None

    @property
    def is_green(self) -> bool:
        return self.mrz is not None and self.outcome.is_green

    @property
    def flags(self) -> list[Flag]:
        return self.outcome.flags

    def to_fields(self) -> dict:
        """Kontrol ekranının sağ panelindeki 4 alan + meta."""
        if self.mrz is None:
            return {"nationality": "", "sex": "", "name": "", "passport_no": "",
                    "green": False, "flags": [f.value for f in self.flags],
                    "error": self.error, "source": self.source}
        return {
            "nationality": self.mrz.nationality,     # alpha-3 -> planlama col 2
            "sex": self.mrz.sex,                      # M/F -> planlama col 3
            "name": self.mrz.name,                    # -> planlama col 4
            "passport_no": self.mrz.document_number,  # -> planlama col 20
            "birth_date": self.mrz.birth_date.isoformat() if self.mrz.birth_date else None,
            "expiry_date": self.mrz.expiry_date.isoformat() if self.mrz.expiry_date else None,
            "green": self.is_green,
            "flags": [f.value for f in self.flags],
            "checks": self.mrz.checks,
            "error": None,
            "source": self.source,
        }


def _make_client(api_key: Optional[str] = None):
    import anthropic  # geç import: paket yoksa sadece bu yol patlar
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()


def extract_passengers_from_vision(image_bytes: bytes, media_type: str, *, client=None,
                                     model: Optional[str] = None,
                                     provider: str = settings_mod.VISION_MODE_CLAUDE,
                                     settings: Optional[settings_mod.Settings] = None) -> list[dict]:
    """Claude Vision -> list of passengers (each with format, lines, fields)."""
    settings = settings or settings_mod.Settings()
    if provider == settings_mod.VISION_MODE_GOOGLE_VISION:
        fmt, lines, fields = extract_with_google_vision(
            image_bytes,
            credentials_json=settings.google_credentials_json,
            use_document_text=settings.google_vision_document_text,
        )
        return [{"format": fmt, "lines": lines, "fields": fields}]
    client = client or _make_client()
    model = model or settings_mod.DEFAULT_MODEL
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64",
                                             "media_type": media_type, "data": b64}},
                {"type": "text", "text": "Extract all passenger information."},
            ],
        }],
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    )
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
    try:
        data = json.loads(text)
        return data.get("passengers", [])
    except json.JSONDecodeError:
        return []


def process_image(
    image_bytes: bytes,
    *,
    source: str = "",
    media_type: str = "image/jpeg",
    client=None,
    model: Optional[str] = None,
    provider: str = settings_mod.VISION_MODE_CLAUDE,
    settings: Optional[settings_mod.Settings] = None,
    seen_document_numbers: Optional[set[str]] = None,
    today: Optional[_dt.date] = None,
) -> list[PassportRecord]:
    """Uçtan uca: görsel -> yolcu listesi -> parse + checksum -> flag'ler -> list[PassportRecord]."""
    try:
        passengers = extract_passengers_from_vision(
            image_bytes,
            media_type,
            client=client,
            model=model,
            provider=provider,
            settings=settings,
        )
    except Exception as e:
        return [PassportRecord(source=source, mrz=None,
                               outcome=ValidationOutcome(flags=[Flag.UNREADABLE]),
                               error=f"{type(e).__name__}: {e}")]

    if not passengers:
        return [PassportRecord(source=source, mrz=None,
                               outcome=ValidationOutcome(flags=[Flag.UNREADABLE]),
                               error="Yolcu/MRZ bulunamadı")]

    records = []
    for p in passengers:
        fmt = p.get("format", "NONE")
        lines = [ln for ln in p.get("lines", []) if ln.strip()]
        fields = p.get("fields", {})

        if fmt == "NONE" and any([fields.get("name"), fields.get("passport_no"), fields.get("nationality")]):
            from app.mrz.parser import MRZResult
            mrz = MRZResult(
                format="NONE",
                document_type="ID",
                issuing_country=fields.get("nationality", "")[:3] if fields.get("nationality") else "",
                nationality=fields.get("nationality", "")[:3] if fields.get("nationality") else "",
                document_number=fields.get("passport_no", ""),
                sex=fields.get("sex", "X") or "X",
                surname="",
                given_names=fields.get("name", ""),
                birth_date=None,
                expiry_date=None,
                checks={},
                raw_lines=[]
            )
            outcome = validate_mrz(mrz, seen_document_numbers=seen_document_numbers, today=today)
            outcome.add(Flag.FREE_TEXT_UNVERIFIED)
            records.append(PassportRecord(source=source, mrz=mrz, outcome=outcome))
            continue

        try:
            mrz = None
            if fmt == "TR_ID_FRONT":
                from app.mrz.parser import MRZResult
                mrz = MRZResult(
                    format="TR_ID_FRONT",
                    document_type="ID",
                    issuing_country="TUR",
                    nationality="TUR",
                    document_number=fields.get("tc_no", ""),
                    sex=fields.get("gender", "X"),
                    surname=fields.get("surname", ""),
                    given_names=fields.get("name", ""),
                    birth_date=None,
                    expiry_date=None,
                    checks={"id_front": True},
                    raw_lines=[]
                )
            elif fmt == "TD3" and len(lines) >= 2:
                mrz = parse_td3(lines[0], lines[1], today=today)
                if mrz.document_number and "document_number" in mrz.checks and not mrz.checks["document_number"]:
                    raw_text = fields.get("raw_text", "")
                    if raw_text:
                        expected_check_char = lines[1][9]
                        expected_check = 0 if expected_check_char == '<' else int(expected_check_char) if expected_check_char.isdigit() else -1
                        if expected_check != -1:
                            import re
                            from app.mrz.checksum import check_digit
                            flat = re.sub(r'[^A-Z0-9]', '', raw_text.upper())
                            bad_num = mrz.document_number
                            best_cand = bad_num
                            min_dist = 999
                            for i in range(len(flat) - len(bad_num) + 1):
                                cand = flat[i:i+len(bad_num)]
                                if check_digit(cand) == expected_check:
                                    dist = sum(1 for a, b in zip(cand, bad_num) if a != b)
                                    if 0 < dist <= 3 and dist < min_dist:
                                        min_dist = dist
                                        best_cand = cand
                            if best_cand != bad_num:
                                mrz.document_number = best_cand
                                mrz.checks["document_number"] = True
                                mrz.checks["composite"] = True
            elif fmt == "TD1" and len(lines) >= 3:
                mrz = parse_td1(lines[0], lines[1], lines[2], today=today)
                if mrz.document_number and "document_number" in mrz.checks and not mrz.checks["document_number"]:
                    raw_text = fields.get("raw_text", "")
                    if raw_text:
                        expected_check_char = lines[0][14]
                        expected_check = 0 if expected_check_char == '<' else int(expected_check_char) if expected_check_char.isdigit() else -1
                        if expected_check != -1:
                            import re
                            from app.mrz.checksum import check_digit
                            flat = re.sub(r'[^A-Z0-9]', '', raw_text.upper())
                            bad_num = mrz.document_number
                            best_cand = bad_num
                            min_dist = 999
                            for i in range(len(flat) - len(bad_num) + 1):
                                cand = flat[i:i+len(bad_num)]
                                if check_digit(cand) == expected_check:
                                    dist = sum(1 for a, b in zip(cand, bad_num) if a != b)
                                    if 0 < dist <= 3 and dist < min_dist:
                                        min_dist = dist
                                        best_cand = cand
                            if best_cand != bad_num:
                                mrz.document_number = best_cand
                                mrz.checks["document_number"] = True
                                mrz.checks["composite"] = True
                if mrz.issuing_country == "TUR" or mrz.nationality == "TUR":
                    tc = _tr_tc_no_from_line1(mrz.raw_lines[0]) if mrz.raw_lines else None
                    if tc:
                        mrz.document_number = tc
            elif fmt == "TC_FRONT":
                from app.mrz.parser import MRZResult
                mrz = MRZResult(
                    format="TC_FRONT",
                    document_type="ID",
                    issuing_country="TUR",
                    nationality="TUR",
                    document_number=fields.get("tc_no", ""),
                    sex=fields.get("gender", "X"),
                    surname=fields.get("surname", ""),
                    given_names=fields.get("name", ""),
                    birth_date=None,
                    expiry_date=None,
                    checks={},
                    raw_lines=[]
                )
            else:
                records.append(PassportRecord(source=source, mrz=None,
                                      outcome=ValidationOutcome(flags=[Flag.UNREADABLE]),
                                      error="MRZ bulunamadı/okunamadı"))
                continue
        except Exception as e:
            records.append(PassportRecord(source=source, mrz=None,
                                  outcome=ValidationOutcome(flags=[Flag.UNREADABLE]),
                                  error=f"parse: {e}"))
            continue

        outcome = validate_mrz(mrz, seen_document_numbers=seen_document_numbers, today=today)
        records.append(PassportRecord(source=source, mrz=mrz, outcome=outcome))

    return records


def process_file(path: str | Path, **kwargs) -> list[PassportRecord]:
    p = Path(path)
    return process_image(p.read_bytes(), source=str(p),
                         media_type=media_type_for(p), **kwargs)
