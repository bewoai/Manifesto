"""Doğrudan Claude sağlayıcısı: görsel → yalnız MRZ satırları (docs/mimari-v2 §3, PR 2).

Model SADECE OCR eder: MRZ satırlarını karakter-karakter döndürür. Parse, checksum ve
yeşil/sarı kararı `app/mrz` + `to_mrz()` içinde, kodda yapılır. Yapılandırılmış çıktı
(`output_config.format`) kullanılır; zorunlu `tool_choice` güncel modellerde 400 döndüğü
için kullanılmaz.
"""
from __future__ import annotations

import base64
import json
from typing import Optional

from app.vision.providers.base import OcrResult

try:  # anthropic paketi yoksa yalnız bu sağlayıcı kullanılamaz
    import anthropic as _anthropic
except Exception:  # pragma: no cover
    _anthropic = None

MRZ_ONLY_SYSTEM = (
    "You are an OCR engine for travel documents. Read the Machine Readable Zone (MRZ) printed "
    "at the bottom of the passport or ID card in the image and return ONLY the MRZ lines, "
    "character-exact. TD3 passports have 2 lines of 44 characters; TD1 identity cards have "
    "3 lines of 30 characters; '<' is the filler character. Do not correct, guess or complete "
    "characters, do not read any other text, and do not translate. If no MRZ is visible, "
    "return format NONE with an empty lines array. Give a confidence between 0 and 1 for how "
    "clearly the MRZ characters were legible."
)

MRZ_SCHEMA = {
    "type": "object",
    "properties": {
        "format": {"type": "string", "enum": ["TD3", "TD1", "NONE"]},
        "lines": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
    "required": ["format", "lines", "confidence"],
    "additionalProperties": False,
}

_USER_TEXT = "Return the MRZ lines of this document."


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


class ClaudeDirectProvider:
    """Anthropic SDK istemcisiyle tek çağrı; anahtar cihazda (DPAPI), sunucu yok."""

    name = "claude_direct"

    def __init__(self, client, model: str, *, effort: str = "low", max_tokens: int = 1024):
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
                system=MRZ_ONLY_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                        {"type": "text", "text": _USER_TEXT},
                    ],
                }],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": MRZ_SCHEMA},
                },
            )
        except Exception as exc:  # SDK hata zinciri _describe_error'da ayrıştırılır
            return OcrResult.failure(_describe_error(exc), source=self.source)

        usage = self._usage(resp)
        if getattr(resp, "stop_reason", None) == "refusal":
            return OcrResult.failure("Model görseli işlemeyi reddetti.", source=self.source)

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
            return OcrResult.failure("Model geçerli bir MRZ çıktısı döndürmedi.", source=self.source)

        fmt = str(data.get("format") or "NONE").upper()
        lines = [str(ln).strip().upper() for ln in (data.get("lines") or []) if str(ln).strip()]
        try:
            score = float(data.get("confidence") or 0.0)
        except (TypeError, ValueError):
            score = 0.0

        if fmt == "NONE" or not lines:
            return OcrResult(
                status="success", passenger={}, confidence="red", raw_text="",
                warnings=["no_mrz"], source=self.source, usage=usage,
            )
        return OcrResult(
            status="success",
            passenger={},                       # alanlar yerel parser'dan gelir
            confidence=_confidence_level(score),
            raw_text="\n".join(lines),
            warnings=[],
            source=self.source,
            usage=usage,
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
