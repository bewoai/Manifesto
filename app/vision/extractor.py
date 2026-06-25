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
    "You must also provide a `confidence` score (between 0.0 and 1.0) for each passenger and an `overall_confidence` score for the entire extraction. "
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
                    "confidence": {"type": "number"},
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
                "required": ["format", "lines", "confidence"]
            }
        },
        "overall_confidence": {"type": "number"}
    },
    "required": ["passengers", "overall_confidence"],
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
    confidence_score: float = 1.0
    processing_route: str = "google_vision"
    ai_model_used: Optional[str] = None
    fallback_reason: Optional[str] = None
    requires_manual_review: bool = False

    @property
    def is_green(self) -> bool:
        return self.mrz is not None and self.outcome.is_green and not self.requires_manual_review

    @property
    def flags(self) -> list[Flag]:
        return self.outcome.flags

    def to_fields(self) -> dict:
        """Kontrol ekranının sağ panelindeki 4 alan + meta."""
        if self.mrz is None:
            return {"nationality": "", "sex": "", "name": "", "passport_no": "",
                    "green": False, "flags": [f.value for f in self.flags],
                    "error": self.error, "source": self.source,
                    "confidence_score": self.confidence_score,
                    "processing_route": self.processing_route,
                    "requires_manual_review": self.requires_manual_review}
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
            "confidence_score": self.confidence_score,
            "processing_route": self.processing_route,
            "ai_model_used": self.ai_model_used,
            "requires_manual_review": self.requires_manual_review
        }


def _make_client(api_key: Optional[str] = None):
    import anthropic  # geç import: paket yoksa sadece bu yol patlar
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()


def _normalize_anthropic_payload(payload: dict) -> dict:
    """Eski tek-belge ve yeni çok-yolcu yanıtlarını aynı sözleşmeye çevir."""
    if not isinstance(payload, dict):
        return {"passengers": [], "overall_confidence": 0.0}
    if isinstance(payload.get("passengers"), list):
        return {
            **payload,
            "overall_confidence": float(payload.get("overall_confidence", 0.0) or 0.0),
        }
    if payload.get("format") or payload.get("lines"):
        passenger = {
            "format": payload.get("format", "NONE"),
            "lines": payload.get("lines") or payload.get("mrz_lines") or [],
            "confidence": float(payload.get("confidence", 1.0) or 0.0),
            "fields": payload.get("fields") or {},
        }
        return {
            "passengers": [passenger],
            "overall_confidence": passenger["confidence"],
        }
    return {"passengers": [], "overall_confidence": 0.0}


def call_anthropic(image_bytes: bytes, media_type: str, client, model: str, system_prompt: str) -> dict:
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64",
                                                 "media_type": media_type, "data": b64}},
                    {"type": "text", "text": "Extract all passenger information. If the document is unreadable or not a passenger list/ID, return empty passengers array."},
                ],
            }],
            tools=[{
                "name": "record_passengers",
                "description": "Record extracted passengers",
                "input_schema": OUTPUT_SCHEMA
            }],
            tool_choice={"type": "tool", "name": "record_passengers"}
        )
        tool_use = next((b for b in resp.content if getattr(b, "type", None) == "tool_use"), None)
        if tool_use and isinstance(tool_use.input, dict):
            return _normalize_anthropic_payload(tool_use.input)
        text_block = next(
            (
                block for block in resp.content
                if getattr(block, "type", None) == "text"
                and getattr(block, "text", None)
            ),
            None,
        )
        if text_block:
            return _normalize_anthropic_payload(json.loads(text_block.text))
    except Exception as e:
        print(f"Anthropic API Error ({model}): {e}")
        return {"passengers": [], "overall_confidence": 0.0, "_error": str(e)}
    return {
        "passengers": [],
        "overall_confidence": 0.0,
        "_error": "Model geçerli bir yolcu sonucu döndürmedi.",
    }


def _process_with_injected_client(
    image_bytes: bytes,
    *,
    source: str,
    media_type: str,
    client,
    model: Optional[str],
    settings: settings_mod.Settings,
    seen_document_numbers: Optional[set[str]],
    today: Optional[_dt.date],
) -> list[PassportRecord]:
    """Test ve geliştirici araçları için açıkça verilen istemciyi kullan."""
    main_model = model or settings.model or settings_mod.DEFAULT_MODEL
    fallback_model = settings.anthropic_fallback_model or settings_mod.FALLBACK_MODEL
    result = call_anthropic(image_bytes, media_type, client, main_model, SYSTEM_PROMPT)
    passengers = result.get("passengers", [])
    overall_confidence = float(result.get("overall_confidence", 0.0) or 0.0)
    main_error = result.get("_error")
    ai_model = main_model
    route = "google_vision_plus_sonnet"
    fallback_reason = None

    if not passengers or overall_confidence < settings.ai_confidence_threshold_fallback:
        fallback_reason = (
            f"{main_model} yolcu bulamadı"
            if not passengers
            else f"{main_model} güven skoru ({overall_confidence}) düşük"
        )
        ai_model = fallback_model
        route = "google_vision_plus_opus"
        result = call_anthropic(
            image_bytes, media_type, client, fallback_model, SYSTEM_PROMPT
        )
        passengers = result.get("passengers", [])

    if not passengers:
        detail = result.get("_error") or main_error
        error = "Yolcu/MRZ bulunamadı"
        if detail:
            error = f"{error}: {detail}"
        return [PassportRecord(
            source=source,
            mrz=None,
            outcome=ValidationOutcome(flags=[Flag.UNREADABLE]),
            error=error,
            confidence_score=0.0,
            processing_route=route,
            ai_model_used=ai_model,
            fallback_reason=fallback_reason,
            requires_manual_review=True,
        )]

    records = _parse_and_validate_mrz(
        passengers, source, seen_document_numbers, today
    )
    for record in records:
        record.processing_route = route
        record.ai_model_used = ai_model
        record.fallback_reason = fallback_reason
        if record.confidence_score < settings.ai_confidence_threshold_manual_review:
            record.requires_manual_review = True
            record.outcome.add(Flag.LOW_CONFIDENCE)
    return records

def process_image(
    image_bytes: bytes,
    *,
    source: str = "",
    media_type: str = "image/jpeg",
    client=None,
    model: Optional[str] = None,
    provider: str = settings_mod.VISION_MODE_IRTIFA_SERVER,
    settings: Optional[settings_mod.Settings] = None,
    seen_document_numbers: Optional[set[str]] = None,
    today: Optional[_dt.date] = None,
) -> list[PassportRecord]:
    """Uçtan uca: görsel -> Irtifa OCR Sunucusu -> list[PassportRecord].
    Müşteri sürümünde (Customer Build) yerel Google Vision veya Claude fallback devre dışıdır.
    SADECE Irtifa sunucusu kullanılır.
    """
    settings = settings or settings_mod.Settings()

    # Üretim sürümü merkezi OCR sunucusunu kullanır. Açıkça istemci verilmesi
    # yalnız test/geliştirici doğrulaması içindir ve dağıtılan anahtarları etkilemez.
    if client is not None:
        return _process_with_injected_client(
            image_bytes,
            source=source,
            media_type=media_type,
            client=client,
            model=model,
            settings=settings,
            seen_document_numbers=seen_document_numbers,
            today=today,
        )
    
    # Müşteri derlemesinde provider ne olursa olsun her zaman Irtifa Server kullanılır.
    from app.vision.irtifa_client import call_irtifa_ocr_server
    mrz, outcome, error_msg, conf, route, ai_model = call_irtifa_ocr_server(
        image_bytes=image_bytes,
        server_url=settings.irtifa_server_url,
        license_key=settings.irtifa_license_key,
        device_id=settings.irtifa_device_id,
        media_type=media_type,
    )
    
    if mrz is not None:
        local_outcome = validate_mrz(
            mrz,
            seen_document_numbers=seen_document_numbers,
            today=today,
        )
        for flag in local_outcome.flags:
            outcome.add(flag)
        if not all((mrz.nationality, mrz.document_number, mrz.name, mrz.sex)):
            outcome.add(Flag.MISSING_REQUIRED_FIELDS)

    req_manual = False
    if error_msg or conf < settings.ai_confidence_threshold_manual_review:
        req_manual = True
        if not error_msg:
            outcome.add(Flag.LOW_CONFIDENCE)
            
    return [PassportRecord(
        source=source,
        mrz=mrz,
        outcome=outcome,
        error=error_msg,
        confidence_score=conf,
        processing_route=route,
        ai_model_used=ai_model,
        requires_manual_review=req_manual
    )]


def _parse_and_validate_mrz(passengers: list[dict], source: str, seen_document_numbers: Optional[set[str]], today: Optional[_dt.date]) -> list[PassportRecord]:
    records = []
    seen_in_batch = set(seen_document_numbers or ())
    for p in passengers:
        fmt = p.get("format", "NONE")
        lines = [ln for ln in p.get("lines", []) if ln.strip()]
        fields = p.get("fields", {})
        conf = p.get("confidence", 1.0)

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
            outcome = validate_mrz(mrz, seen_document_numbers=seen_in_batch, today=today)
            outcome.add(Flag.FREE_TEXT_UNVERIFIED)
            records.append(PassportRecord(source=source, mrz=mrz, outcome=outcome, confidence_score=conf))
            if mrz.document_number:
                seen_in_batch.add(mrz.document_number)
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
                                      error="MRZ bulunamadı/okunamadı", confidence_score=conf))
                continue
        except Exception as e:
            records.append(PassportRecord(source=source, mrz=None,
                                  outcome=ValidationOutcome(flags=[Flag.UNREADABLE]),
                                  error=f"parse: {e}", confidence_score=conf))
            continue

        outcome = validate_mrz(mrz, seen_document_numbers=seen_in_batch, today=today)
        records.append(PassportRecord(source=source, mrz=mrz, outcome=outcome, confidence_score=conf))
        if mrz.document_number:
            seen_in_batch.add(mrz.document_number)

    return records


def process_file(path: str | Path, **kwargs) -> list[PassportRecord]:
    p = Path(path)
    return process_image(p.read_bytes(), source=str(p),
                         media_type=media_type_for(p), **kwargs)

