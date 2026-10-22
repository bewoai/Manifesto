"""İrtifa OCR sunucusu sözleşme testleri (docs/mimari-v2-ocr-sunucu.md §4.2, §5).

Tek doğruluk kaynağı: `tests/contract/fixtures/*.json`. Her fixture bir sunucu yanıtı
(HTTP durum + gövde) ve istemcinin bundan çıkarması gereken sonucu (`expect`) tanımlar.
Aynı fixture'lar ileride `server/` için TestClient ile yanıt şemasını doğrulamakta
kullanılır. Burada istemci tarafı: `requests.post` sahte yanıtla yamalanır, sonuç
`process_image` üzerinden uçtan uca doğrulanır.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from app import settings as settings_mod
from app.validation.flags import Flag
from app.vision.extractor import process_image

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.json"))
TODAY = dt.date(2010, 1, 1)


class FakeResponse:
    def __init__(self, status_code: int, body):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


@pytest.mark.parametrize("fixture_path", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_client_handles_server_fixture(fixture_path, monkeypatch):
    fx = json.loads(fixture_path.read_text(encoding="utf-8"))
    captured = {}

    def fake_post(url, *, headers, files, timeout):
        captured["url"] = url
        captured["headers"] = headers
        return FakeResponse(fx["http_status"], fx.get("body"))

    monkeypatch.setattr("app.vision.irtifa_client.requests.post", fake_post)
    s = settings_mod.Settings(
        irtifa_server_url="https://ocr.example.test", irtifa_license_key="LIC-1", irtifa_device_id="DEV-1"
    )
    rec = process_image(b"img", source="p.jpg", settings=s, today=TODAY)[0]

    assert captured["url"] == "https://ocr.example.test/ocr/passport"
    assert captured["headers"] == {"x-license-key": "LIC-1", "x-device-id": "DEV-1"}

    expect = fx["expect"]
    assert rec.is_green == expect["green"], (rec.flags, rec.error)
    for flag in expect.get("flags", []):
        assert Flag(flag) in rec.flags, (flag, rec.flags)
    if "error_contains" in expect:
        assert rec.error and expect["error_contains"].lower() in rec.error.lower(), rec.error
    else:
        assert rec.error is None
    if "passport_no" in expect:
        assert rec.to_fields()["passport_no"] == expect["passport_no"]
    # Hata → manuel kontrol kuyruğu; sarı kayıtlar pasaport ekranında sarı kart olarak kalır
    if "error_contains" in expect:
        assert rec.requires_manual_review is True


def test_fixture_bodies_follow_contract_schema():
    """200 yanıtları §4.2 gövdesine uymalı: status/passenger/confidence/raw_text/warnings/source."""
    for path in FIXTURES:
        fx = json.loads(path.read_text(encoding="utf-8"))
        if fx["http_status"] != 200 or fx.get("body") is None:
            continue
        body = fx["body"]
        assert body["status"] in ("success", "error"), path.name
        if body["status"] == "success":
            for key in ("passenger", "confidence", "raw_text", "warnings", "source"):
                assert key in body, (path.name, key)
            assert body["confidence"] in ("green", "yellow", "red"), path.name
            assert set(body["passenger"]) <= {
                "first_name", "last_name", "nationality", "gender", "document_no", "birth_date", "expiry_date"
            }, path.name
