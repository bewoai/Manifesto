"""Doğrudan Claude sağlayıcısı: görsel → belge türü + yolcular (MRZ satırları / alanlar).

Sahadan gelen malzeme karışık: MRZ'li pasaport, kimlik ön yüzü, basılı veya el yazısı
yolcu listeleri (işaretli satırlar uçuyor), WhatsApp rezervasyon mesajı ekran görüntüsü.
Model yalnız OKUR: belge türünü sınıflandırır, MRZ varsa satırları karakter-karakter,
yoksa alanları döndürür; satır yanındaki işaretleri (✓, SI, sıra no, fosfor) yorumlamadan
`annotation` olarak taşır. Parse, checksum ve yeşil/sarı kararı `to_records()` içinde,
kodda yapılır. Yapılandırılmış çıktı (`output_config.format`) kullanılır; zorunlu
`tool_choice` güncel modellerde 400 döndüğü için kullanılmaz.
"""
from __future__ import annotations

import base64
import json
from typing import Optional

from app.vision.providers.base import KINDS, OcrResult

try:  # anthropic paketi yoksa yalnız bu sağlayıcı kullanılamaz
    import anthropic as _anthropic
except Exception:  # pragma: no cover
    _anthropic = None

SYSTEM_PROMPT = (
    "You are an OCR and transcription engine for a hot-air balloon operator's passenger "
    "manifest workflow. The image is one of: a passport data page (MRZ at the bottom), an "
    "identity card (front or back; the MRZ is on the back of ID cards), one or more cards in "
    "one photo, a printed passenger list or spreadsheet, a handwritten passenger list, or a "
    "screenshot of chat messages describing reservations (date, hotel, passenger count, then one "
    "line per passenger). The photo may be rotated or skewed; read it in its correct orientation.\n\n"
    "Rules:\n"
    "1. Classify the document into `kind`.\n"
    "2. Return EVERY passenger you can see, one entry each, in reading order. Do not merge, "
    "skip, deduplicate or invent rows. Rows for guides, drivers, pilots or captains are still "
    "returned, with `annotation` describing the role word if printed.\n"
    "3. If a Machine Readable Zone is visible, copy its lines character-exact into `lines` "
    "(TD3: 2 lines of 44 chars; TD1: 3 lines of 30 chars; '<' is the filler). Never correct, "
    "guess or complete MRZ characters. Also fill `fields` from the printed zone when visible.\n"
    "4. Without an MRZ, fill `fields` from what is printed or written: first_name, last_name, "
    "nationality (ISO 3166-1 alpha-3 if the document or list states it; otherwise empty — do "
    "not guess from names), gender (M/F only if stated or clearly implied by a title such as "
    "MR/MRS/MS/SRA; else empty), document_no exactly as written (passport or national ID "
    "number), document_type ('P' passport, 'I' identity card/DNI, '' unknown), birth_date and "
    "expiry_date as ISO 8601 (YYYY-MM-DD). Date formats vary between lists (YYYYMMDD, "
    "DD.MM.YYYY, MM.DD.YYYY, DD-MMM-YY); infer the list's convention from rows where the day is "
    "greater than 12 and apply it to the whole list; if still ambiguous, prefer DD.MM.YYYY and "
    "set confidence below 0.7 for that row. A date like 01/01/9999 means no expiry: leave "
    "expiry_date empty.\n"
    "5. `annotation`: the literal handwritten or visual mark attached to the row, if any — a "
    "tick ('✓'), a highlighted row ('highlight'), a letter or word ('B', 'SI'), a handwritten "
    "number ('21'), a strike-through ('strike'). Empty when the row has no mark. Do NOT decide "
    "who is flying; just report the mark. Set `selected` only when the list itself prints an "
    "explicit yes/no column; otherwise null.\n"
    "6. `group`: header information that applies to the whole image — flight/travel date "
    "(ISO), hotel, agency or tour operator, booking/tour code, declared passenger count (pax), "
    "a nationality stated for the whole group (nationality_hint, alpha-3), and a short note "
    "for anything else relevant (room requests, phone numbers). Empty strings when absent.\n"
    "7. `confidence` per passenger: 0-1, how legible that row was. Give an overall "
    "`confidence` for the image too.\n"
    "Output only the requested JSON."
)

PASSENGER_SCHEMA = {
    "type": "object",
    "properties": {
        "format": {"type": "string", "enum": ["TD3", "TD1", "NONE"]},
        "lines": {"type": "array", "items": {"type": "string"}},
        "fields": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "nationality": {"type": "string"},
                "gender": {"type": "string"},
                "document_no": {"type": "string"},
                "document_type": {"type": "string"},
                "birth_date": {"type": "string"},
                "expiry_date": {"type": "string"},
            },
            "required": ["first_name", "last_name", "nationality", "gender", "document_no",
                         "document_type", "birth_date", "expiry_date"],
            "additionalProperties": False,
        },
        "confidence": {"type": "number"},
        "annotation": {"type": "string"},
        "selected": {"type": ["boolean", "null"]},
    },
    "required": ["format", "lines", "fields", "confidence", "annotation", "selected"],
    "additionalProperties": False,
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": list(KINDS)},
        "group": {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
                "hotel": {"type": "string"},
                "agency": {"type": "string"},
                "booking_code": {"type": "string"},
                "pax": {"type": "integer"},
                "nationality_hint": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["date", "hotel", "agency", "booking_code", "pax", "nationality_hint", "note"],
            "additionalProperties": False,
        },
        "passengers": {"type": "array", "items": PASSENGER_SCHEMA},
        "confidence": {"type": "number"},
    },
    "required": ["kind", "group", "passengers", "confidence"],
    "additionalProperties": False,
}

_USER_TEXT = (
    "Transcribe this document: classify it, then list every passenger with MRZ lines when "
    "visible, otherwise with the printed/handwritten fields, and report any row marks."
)


def _describe_error(exc: Exception) -> str:
    if _anthropic is not None:
        if isinstance(exc, _anthropic.AuthenticationError):
            return "Claude API anahtarı geçersiz veya eksik. Ayarlar'dan kontrol edin."
        if isinstance(exc, _anthropic.PermissionDeniedError):
            return "Claude API anahtarının bu işlem için yetkisi yok."
        if isinstance(exc, _anthropic.RateLimitError):
            return "Claude API istek sınırı aşıldı. Biraz sonra tekrar deneyin."
        if isinstance(exc, _anthropic.APIConnectionError):
            return "Claude API'ye ulaşılamıyor. İnternet bağlantınızı kontrol edin."
        if isinstance(exc, _anthropic.APIStatusError):
            return f"Claude API hatası ({exc.status_code}). Lütfen tekrar deneyin."
    return f"OCR hatası: {exc}"


def _confidence_level(score: float) -> str:
    if score >= 0.9:
        return "green"
    if score >= 0.7:
        return "yellow"
    return "red"


def _clean_passenger(p: dict) -> dict:
    fields = p.get("fields") if isinstance(p.get("fields"), dict) else {}
    cleaned_fields = {k: str(fields.get(k) or "").strip() for k in (
        "first_name", "last_name", "nationality", "gender", "document_no",
        "document_type", "birth_date", "expiry_date",
    )}
    cleaned_fields["nationality"] = cleaned_fields["nationality"].upper()[:3]
    cleaned_fields["gender"] = cleaned_fields["gender"].upper()[:1]
    cleaned_fields["document_type"] = cleaned_fields["document_type"].upper()[:1]
    lines = [str(ln).strip().upper() for ln in (p.get("lines") or []) if str(ln).strip()]
    try:
        score = float(p.get("confidence") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    selected = p.get("selected")
    return {
        "format": str(p.get("format") or ("NONE" if not lines else "")).upper(),
        "lines": lines,
        "fields": cleaned_fields,
        "confidence": _confidence_level(score),
        "annotation": str(p.get("annotation") or "").strip(),
        "selected": selected if isinstance(selected, bool) else None,
    }


class ClaudeDirectProvider:
    """Anthropic SDK istemcisiyle tek çağrı; anahtar cihazda (DPAPI), sunucu yok."""

    name = "claude_direct"

    def __init__(self, client, model: str, *, effort: str = "medium", max_tokens: int = 8192):
        self.client = client
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    @property
    def source(self) -> str:
        return f"claude:{self.model}"

    def read(self, image_bytes: bytes, media_type: str = "image/jpeg") -> OcrResult:
        if not image_bytes:
            return OcrResult.failure("Görsel dosyası boş.", source=self.source)
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                        {"type": "text", "text": _USER_TEXT},
                    ],
                }],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
                },
            )
        except Exception as exc:  # SDK hata zinciri _describe_error'da ayrıştırılır
            return OcrResult.failure(_describe_error(exc), source=self.source)

        usage = self._usage(resp)
        if getattr(resp, "stop_reason", None) == "refusal":
            return OcrResult.failure("Model görseli işlemeyi reddetti.", source=self.source)
        if getattr(resp, "stop_reason", None) == "max_tokens":
            return OcrResult.failure(
                "Liste çok uzun, çıktı kesildi. Görseli bölerek (daha az satır) tekrar deneyin.",
                source=self.source,
            )

        text = next(
            (getattr(b, "text", None) for b in getattr(resp, "content", []) or []
             if getattr(b, "type", None) == "text" and getattr(b, "text", None)),
            None,
        )
        try:
            data = json.loads(text) if text else None
        except ValueError:
            data = None
        if not isinstance(data, dict):
            return OcrResult.failure("Model geçerli bir çıktı döndürmedi.", source=self.source)

        kind = str(data.get("kind") or "other")
        if kind not in KINDS:
            kind = "other"
        group_raw = data.get("group") if isinstance(data.get("group"), dict) else {}
        group = {k: (group_raw.get(k) if k == "pax" else str(group_raw.get(k) or "").strip())
                 for k in ("date", "hotel", "agency", "booking_code", "pax", "nationality_hint", "note")}
        group["nationality_hint"] = str(group["nationality_hint"] or "").upper()[:3]
        if not isinstance(group.get("pax"), int):
            group["pax"] = None
        passengers = [_clean_passenger(p) for p in (data.get("passengers") or []) if isinstance(p, dict)]
        try:
            overall = float(data.get("confidence") or 0.0)
        except (TypeError, ValueError):
            overall = 0.0

        first = passengers[0] if passengers else None
        return OcrResult(
            status="success",
            passenger={},                                   # alanlar to_records'ta yolcu başına işlenir
            confidence=_confidence_level(overall),
            raw_text="\n".join(first["lines"]) if first and first["lines"] else "",
            warnings=[] if passengers else ["no_passengers"],
            source=self.source,
            usage=usage,
            kind=kind,
            group=group,
            passengers=passengers,
        )

    @staticmethod
    def _usage(resp) -> Optional[dict]:
        u = getattr(resp, "usage", None)
        if u is None:
            return None
        out = {}
        for key in ("input_tokens", "output_tokens", "cache_read_input_tokens"):
            value = getattr(u, key, None)
            if isinstance(value, int):
                out[key] = value
        return out or None
