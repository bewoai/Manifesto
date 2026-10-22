"""İrtifa OCR sunucusu istemcisi — geriye uyumlu sarıcı.

Asıl iş `app/vision/providers/irtifa_server.py` (HTTP) ve
`app/vision/providers/base.py` (`to_mrz`: yerel MRZ checksum doğrulaması) içinde.
Bu modül eski çağrı imzasını korur; `requests` burada da import edilir ki
testler `app.vision.irtifa_client.requests.post`'u yamalayabilsin.
"""
from __future__ import annotations

from typing import Optional, Tuple

import requests  # noqa: F401  (testler için; sağlayıcı aynı modül nesnesini kullanır)

from app.mrz.parser import MRZResult
from app.validation.flags import ValidationOutcome
from app.vision.providers.base import (  # noqa: F401  (geriye uyumlu re-export)
    normalize_doc_no as _normalize_doc_no,
    to_mrz,
    verify_against_local_mrz as _verify_against_local_mrz,
)
from app.vision.providers.irtifa_server import IrtifaServerProvider


def call_irtifa_ocr_server(
    image_bytes: bytes,
    server_url: str,
    license_key: str,
    device_id: str,
    media_type: str = "image/jpeg",
    timeout_seconds: int = 45,
) -> Tuple[Optional[MRZResult], ValidationOutcome, Optional[str], float, str, Optional[str]]:
    """Sunucuya OCR isteği gönderir, sonucu yerel checksum'dan geçirir.

    Dönüş: (mrz, outcome, error_msg, confidence_score, processing_route, ai_model_used)
    """
    provider = IrtifaServerProvider(server_url, license_key, device_id, timeout_seconds=timeout_seconds)
    result = provider.read(image_bytes, media_type)
    return to_mrz(result, provider_name=provider.name)
