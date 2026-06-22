"""Vision pipeline testleri — Claude çağrısı sahte (mock) client ile taklit edilir.

Gerçek API anahtarı/ağ GEREKMEZ: fake client MRZ satırlarını döndürür, geri kalan
hat (parse + checksum + flag) gerçek kodla çalışır.
"""
from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

from app.validation.flags import Flag
from app.vision.extractor import process_image

TD3_L1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
TD3_L2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"


class FakeClient:
    """anthropic.Anthropic yerine geçer; sabit MRZ JSON döndürür."""
    def __init__(self, payload: dict):
        self._payload = payload
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        text = json.dumps(self._payload)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def test_process_image_green_for_valid_passport():
    client = FakeClient({"format": "TD3", "lines": [TD3_L1, TD3_L2]})
    # expiry 2012 -> bugünü 2010 alıp expired flag'ini devre dışı bırak
    rec = process_image(b"fake-bytes", source="p.jpg", client=client,
                        today=dt.date(2010, 1, 1))
    assert rec.mrz is not None
    f = rec.to_fields()
    assert f["nationality"] == "UTO"
    assert f["sex"] == "F"
    assert f["name"] == "ANNA MARIA ERIKSSON"
    assert f["passport_no"] == "L898902C3"
    assert rec.is_green
    assert f["green"] is True


def test_expired_passport_is_yellow():
    client = FakeClient({"format": "TD3", "lines": [TD3_L1, TD3_L2]})
    rec = process_image(b"x", client=client, today=dt.date(2026, 6, 22))
    assert not rec.is_green
    assert Flag.EXPIRED in rec.flags


def test_duplicate_document_flagged():
    client = FakeClient({"format": "TD3", "lines": [TD3_L1, TD3_L2]})
    rec = process_image(b"x", client=client, today=dt.date(2010, 1, 1),
                        seen_document_numbers={"L898902C3"})
    assert Flag.DUPLICATE in rec.flags


def test_no_mrz_is_unreadable():
    client = FakeClient({"format": "NONE", "lines": []})
    rec = process_image(b"x", client=client)
    assert rec.mrz is None
    assert Flag.UNREADABLE in rec.flags
    assert rec.to_fields()["green"] is False


def test_checksum_fail_is_yellow():
    bad_l2 = TD3_L2[:9] + "5" + TD3_L2[10:]   # belge no check digit bozuk
    client = FakeClient({"format": "TD3", "lines": [TD3_L1, bad_l2]})
    rec = process_image(b"x", client=client, today=dt.date(2010, 1, 1))
    assert Flag.CHECKSUM_FAIL in rec.flags
    assert not rec.is_green


def test_api_error_does_not_crash():
    class Boom:
        def __init__(self):
            self.messages = SimpleNamespace(create=self._raise)
        def _raise(self, **kw):
            raise RuntimeError("network down")
    rec = process_image(b"x", client=Boom())
    assert Flag.UNREADABLE in rec.flags
    assert "network down" in (rec.error or "")
