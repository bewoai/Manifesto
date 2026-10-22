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
    """Sunucu ne derse desin expired/duplicate yerel hesaplanır (OcrProvider sözleşmesi)."""
    from app.vision.providers import IrtifaServerProvider, OcrResult

    def fake_read(self, image_bytes, media_type="image/jpeg"):
        return OcrResult(
            status="success",
            passenger={"first_name": "AYSE", "last_name": "YILMAZ", "nationality": "TUR",
                       "gender": "F", "document_no": "U123456", "expiry_date": "2020-01-01"},
            confidence="green", raw_text="", source="google_vision",
        )

    monkeypatch.setattr(IrtifaServerProvider, "read", fake_read)
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
    assert Flag.FREE_TEXT_UNVERIFIED in record.flags   # MRZ metni yok → doğrulanmamış
    assert not record.is_green
    assert record.ai_model_used == "google_vision"


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


# ─── Brief §6: sunucu sonucu yerel MRZ check digit ile doğrulanmalı ───────────

TD3_L1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
TD3_L2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"


def _server_payload(document_no: str, raw_text: str) -> dict:
    return {
        "status": "success",
        "source": "google_vision",
        "confidence": "green",
        "passenger": {
            "first_name": "ANNA MARIA",
            "last_name": "ERIKSSON",
            "nationality": "UTO",
            "gender": "F",
            "document_no": document_no,
            "birth_date": "1974-08-12",
            "expiry_date": "2012-04-15",
        },
        "raw_text": raw_text,
        "warnings": [],
    }


def _call(monkeypatch, payload):
    monkeypatch.setattr(
        "app.vision.irtifa_client.requests.post",
        lambda url, *, headers, files, timeout: FakeResponse(200, payload),
    )
    mrz, outcome, error, _, _, _ = call_irtifa_ocr_server(b"img", "https://example.test", "LICENSE", "DEVICE")
    assert error is None
    return mrz, outcome


def test_server_green_without_mrz_is_not_green(monkeypatch):
    from app.validation.flags import validate_mrz

    mrz, _ = _call(monkeypatch, _server_payload("L898902C3", raw_text="Name: ANNA ERIKSSON"))
    assert mrz.checks == {}
    assert not mrz.checks_ok
    outcome = validate_mrz(mrz, today=dt.date(2010, 1, 1))
    assert Flag.FREE_TEXT_UNVERIFIED in outcome.flags
    assert not outcome.is_green


def test_server_result_verified_by_local_mrz(monkeypatch):
    from app.validation.flags import validate_mrz

    mrz, _ = _call(monkeypatch, _server_payload("L898902C3", raw_text="junk\n" + TD3_L1 + "\n" + TD3_L2 + "\n"))
    assert mrz.checks["document_number"] is True
    assert mrz.checks["server_document_match"] is True
    assert mrz.checks_ok, mrz.checks
    assert validate_mrz(mrz, today=dt.date(2010, 1, 1)).is_green


def test_server_document_no_mismatching_mrz_fails_checksum(monkeypatch):
    from app.validation.flags import validate_mrz

    mrz, _ = _call(monkeypatch, _server_payload("X9999999", raw_text=TD3_L1 + "\n" + TD3_L2))
    assert mrz.checks["server_document_match"] is False
    assert not mrz.checks_ok
    assert Flag.CHECKSUM_FAIL in validate_mrz(mrz, today=dt.date(2010, 1, 1)).flags


def test_server_fills_missing_fields_from_verified_mrz(monkeypatch):
    payload = _server_payload("", raw_text=TD3_L1 + "\n" + TD3_L2)
    payload["passenger"]["nationality"] = ""
    payload["passenger"]["gender"] = ""
    mrz, _ = _call(monkeypatch, payload)
    assert mrz.document_number == "L898902C3"
    assert mrz.nationality == "UTO"
    assert mrz.sex == "F"
    assert mrz.checks_ok
