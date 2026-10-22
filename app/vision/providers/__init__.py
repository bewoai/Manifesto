"""OCR sağlayıcıları (docs/mimari-v2-ocr-sunucu.md §4.1).

Her sağlayıcı yalnız OCR eder ve `OcrResult` döner; yeşil/sarı kararı sağlayıcıda
değil, `to_mrz()` içinde yerel MRZ parser + ICAO checksum ile verilir (brief §6).
"""
from app.vision.providers.base import OcrProvider, OcrResult, to_mrz  # noqa: F401
from app.vision.providers.claude_direct import ClaudeDirectProvider  # noqa: F401
from app.vision.providers.irtifa_server import IrtifaServerProvider  # noqa: F401
