"""İrtifa OCR sunucusu sağlayıcısı (HTTP sözleşmesi: docs/mimari-v2-ocr-sunucu.md §4.2)."""
from __future__ import annotations

import logging

import requests

from app.vision.providers.base import CONFIDENCE_LEVELS, KINDS, OcrResult

logger = logging.getLogger("irtifa_ocr")

_EXTENSIONS = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024


class IrtifaServerProvider:
    """`POST {server_url}/ocr/passport` — x-license-key + x-device-id başlıklarıyla."""

    name = "irtifa_server"

    def __init__(self, server_url: str, license_key: str, device_id: str, *, timeout_seconds: int = 45):
        self.server_url = (server_url or "").strip()
        self.license_key = (license_key or "").strip()
        self.device_id = (device_id or "").strip()
        self.timeout_seconds = timeout_seconds

    def read(self, image_bytes: bytes, media_type: str = "image/jpeg") -> OcrResult:
        if not self.license_key:
            return OcrResult.failure("OCR için lisans anahtarı gerekli.", source=self.name)
        if not image_bytes:
            return OcrResult.failure("Görsel dosyası boş.", source=self.name)
        if len(image_bytes) > _MAX_IMAGE_BYTES:
            return OcrResult.failure("Görsel en fazla 10 MB olabilir.", source=self.name)
        if not self.device_id:
            return OcrResult.failure("Cihaz kimliği oluşturulamadı.", source=self.name)
        if not self.server_url:
            return OcrResult.failure("Sunucu adresi belirtilmedi.", source=self.name)

        endpoint = self.server_url.rstrip("/") + "/ocr/passport"
        headers = {"x-license-key": self.license_key, "x-device-id": self.device_id}
        files = {"file": (f"passport.{_EXTENSIONS.get(media_type, 'jpg')}", image_bytes, media_type)}

        try:
            response = requests.post(endpoint, headers=headers, files=files, timeout=self.timeout_seconds)
        except requests.exceptions.RequestException as exc:
            logger.warning("OCR sunucusuna ulaşılamadı: %s", exc)
            return OcrResult.failure(
                "OCR servisine ulaşılamıyor. İnternet bağlantınızı kontrol edin veya daha sonra tekrar deneyin.",
                source=self.name,
            )

        if response.status_code != 200:
            return OcrResult.failure(self._error_message(response), source=self.name)

        try:
            data = response.json()
        except ValueError:
            return OcrResult.failure("Sunucudan geçersiz yanıt alındı.", source=self.name)
        if not isinstance(data, dict):
            return OcrResult.failure("Sunucudan geçersiz yanıt alındı.", source=self.name)
        if data.get("status") != "success":
            return OcrResult.failure(str(data.get("error") or "Sunucu bir hata döndürdü."), source=self.name)

        passenger = data.get("passenger") if isinstance(data.get("passenger"), dict) else {}
        confidence = data.get("confidence") if data.get("confidence") in CONFIDENCE_LEVELS else "red"
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
        # Çok yolculu sözleşme (isteğe bağlı alanlar; eski sunucu yalnız `passenger` döner)
        kind = data.get("kind") if data.get("kind") in KINDS else ("passport_mrz" if data.get("raw_text") else "other")
        group = data.get("group") if isinstance(data.get("group"), dict) else {}
        passengers = [p for p in (data.get("passengers") or []) if isinstance(p, dict)]
        return OcrResult(
            status="success",
            passenger=passenger,
            confidence=confidence,
            raw_text=str(data.get("raw_text") or ""),
            warnings=[str(w) for w in (data.get("warnings") or [])],
            source=str(data.get("source") or self.name),
            usage=usage,
            kind=kind,
            group=group,
            passengers=passengers,
        )

    @staticmethod
    def _error_message(response) -> str:
        code = response.status_code
        if code in (401, 403):
            try:
                detail = str(response.json().get("detail", "")).lower()
            except Exception:
                detail = ""
            if "device" in detail:
                return "Bu lisans başka bir bilgisayara kilitli. Yöneticinizle iletişime geçin."
            if "required" in detail:
                return "OCR için lisans anahtarı gerekli."
            if "expired" in detail:
                return "Lisans süresi dolmuş. Yöneticinizle iletişime geçin."
            if "disabled" in detail:
                return "Paketinizde OCR kapalı. Yöneticinizle iletişime geçin."
            return "Lisans anahtarı geçersiz. OCR işlemi başlatılamaz."
        if code == 400:
            return "Desteklenmeyen dosya türü."
        if code == 413:
            return "Dosya boyutu çok büyük."
        if code == 429:
            return "OCR kullanım kotası doldu. Daha sonra tekrar deneyin veya yöneticinizle iletişime geçin."
        return "OCR servisi geçici bir hata verdi. Lütfen tekrar deneyin."
