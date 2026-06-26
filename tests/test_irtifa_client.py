from __future__ import annotations

import datetime as dt

from app import settings as settings_mod
from app.mrz.parser import MRZResult
from app.validation.flags import Flag, ValidationOutcome
from app.vision.extractor import process_image
from app.vision.irtifa_client import call_irtifa_ocr_server
from app.main import (
    _is_operational_ocr_error,
    _passport_content_type,
    _validate_passport_upload,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


def test_server_client_preserves_image_media_type(monkeypatch):
    captured = {}

    def fake_post(url, *, headers, files, timeout):
        captured["file"] = files["file"]
        return FakeResponse(429)

    monkeypatch.setattr("app.vision.irtifa_client.requests.post", fake_post)
    _, _, error, _, _, _ = call_irtifa_ocr_server(
        b"png-bytes",
        "https://example.test",
        "LICENSE",
        "DEVICE",
        media_type="image/png",
    )
    assert captured["file"][0] == "passport.png"
    assert captured["file"][2] == "image/png"
    assert "kota" in error.lower()


def test_server_client_rejects_large_image_without_network(monkeypatch):
    def fail_post(*args, **kwargs):
        raise AssertionError("Ağ isteği yapılmamalıydı.")

    monkeypatch.setattr("app.vision.irtifa_client.requests.post", fail_post)
    _, _, error, _, _, _ = call_irtifa_ocr_server(
        b"x" * (10 * 1024 * 1024 + 1),
        "https://example.test",
        "LICENSE",
        "DEVICE",
    )
    assert "10 MB" in error


def test_server_result_gets_local_expiry_and_duplicate_checks(monkeypatch):
    mrz = MRZResult(
        format="SERVER_OCR",
        document_type="P",
        issuing_country="TUR",
        nationality="TUR",
        document_number="U123456",
        sex="F",
        surname="YILMAZ",
        given_names="AYSE",
        birth_date=None,
        expiry_date=dt.date(2020, 1, 1),
        checks={},
        raw_lines=[],
    )

    def fake_server(**kwargs):
        return (
            mrz,
            ValidationOutcome(),
            None,
            1.0,
            "irtifa_server",
            "google_vision",
        )

    monkeypatch.setattr(
        "app.vision.irtifa_client.call_irtifa_ocr_server",
        fake_server,
    )
    settings = settings_mod.Settings(
        irtifa_license_key="LICENSE",
        irtifa_device_id="DEVICE",
    )
    record = process_image(
        b"image",
        settings=settings,
        seen_document_numbers={"U123456"},
        today=dt.date(2026, 1, 1),
    )[0]
    assert Flag.EXPIRED in record.flags
    assert Flag.DUPLICATE in record.flags
    assert not record.is_green


def test_operational_errors_do_not_belong_in_manual_review():
    assert _is_operational_ocr_error("OCR için lisans anahtarı gerekli.")
    assert _is_operational_ocr_error("OCR servisine ulaşılamıyor.")
    assert not _is_operational_ocr_error("MRZ bulunamadı/okunamadı")


def test_passport_upload_validation_rejects_bad_files():
    _validate_passport_upload(b"image", "image/png")

    try:
        _validate_passport_upload(b"image", "application/pdf")
    except ValueError as exc:
        assert "JPG" in str(exc)
    else:
        raise AssertionError("PDF dosyası kabul edilmemeliydi.")

    try:
        _validate_passport_upload(b"", "image/jpeg")
    except ValueError as exc:
        assert "boş" in str(exc)
    else:
        raise AssertionError("Boş görsel kabul edilmemeliydi.")


def test_passport_content_type_falls_back_to_supported_extension_only():
    assert _passport_content_type("scan.jpg", "") == "image/jpeg"
    assert _passport_content_type("scan.webp", "application/octet-stream") == "image/webp"
    assert _passport_content_type("scan.pdf", "application/octet-stream") == "application/octet-stream"
