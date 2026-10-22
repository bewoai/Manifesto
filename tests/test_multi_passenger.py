"""Çok yolculu sözleşme: listeler, kimlik ön yüzü, grup başlığı, işaretler, EXIF yönü."""
from __future__ import annotations

import datetime as dt
import io
import json
from types import SimpleNamespace

from app import settings as settings_mod
from app.validation.flags import Flag
from app.vision.extractor import process_image
from app.vision.providers import ClaudeDirectProvider, IrtifaServerProvider, OcrResult
from app.vision.providers.base import to_records
from app.vision.providers.image_prep import prepare_image

TD3_L1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
TD3_L2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
TODAY = dt.date(2010, 1, 1)


def _fields(**kw):
    base = {"first_name": "", "last_name": "", "nationality": "", "gender": "", "document_no": "",
            "document_type": "", "birth_date": "", "expiry_date": ""}
    base.update(kw)
    return base


def _passenger(**kw):
    p = {"format": "NONE", "lines": [], "fields": _fields(), "confidence": 0.95, "annotation": "", "selected": None}
    p.update(kw)
    return p


class FakeProvider:
    name = "fake"

    def __init__(self, result):
        self.result = result

    def read(self, image_bytes, media_type):
        return self.result


# ─── to_records: liste → N kayıt ────────────────────────────────────────

def test_printed_list_yields_one_yellow_record_per_row_with_annotation():
    result = OcrResult(
        status="success", source="claude:x", confidence="green", kind="printed_list",
        group={"date": "2026-10-22", "hotel": "", "agency": "Karavan", "booking_code": "", "pax": None,
               "nationality_hint": "", "note": ""},
        passengers=[
            _passenger(fields=_fields(first_name="SUSAN", last_name="HOLDER", nationality="GBR",
                                      document_no="140134006", document_type="P", birth_date="1949-03-16"),
                       annotation="highlight"),
            _passenger(fields=_fields(first_name="TREVOR", last_name="CURNOW", nationality="GBR",
                                      document_no="123715335", document_type="P"),
                       annotation=""),
        ],
    )
    recs = process_image(b"img", ocr_provider=FakeProvider(result), today=TODAY)
    assert len(recs) == 2
    assert [r.annotation for r in recs] == ["highlight", ""]
    assert all(r.source_kind == "printed_list" for r in recs)
    assert all(Flag.FREE_TEXT_UNVERIFIED in r.flags and not r.is_green for r in recs)
    f = recs[0].to_fields()
    assert (f["name"], f["nationality"], f["passport_no"]) == ("SUSAN HOLDER", "GBR", "140134006")
    assert f["source_kind_label"] == "Basılı liste"
    assert f["group"]["agency"] == "Karavan"
    assert f["document_type"] == "P"


def test_group_nationality_hint_fills_missing_nationality():
    result = OcrResult(
        status="success", source="x", kind="handwritten_list",
        group={"nationality_hint": "ITA", "hotel": "Mustafa Hotel", "agency": "", "date": "", "booking_code": "",
               "pax": 12, "note": ""},
        passengers=[_passenger(fields=_fields(first_name="DANIELA", last_name="PICHETTO", document_no="YB5892141",
                                              birth_date="1957-08-02"), confidence=0.8)],
    )
    rec = process_image(b"img", ocr_provider=FakeProvider(result), today=TODAY)[0]
    assert rec.mrz.nationality == "ITA"
    assert rec.group["pax"] == 12
    assert Flag.MISSING_REQUIRED_FIELDS in rec.flags     # cinsiyet yok → operatör doldurur
    assert not rec.is_green


def test_id_front_without_mrz_is_yellow_but_fields_filled():
    result = OcrResult(
        status="success", source="x", kind="id_front",
        passengers=[_passenger(fields=_fields(first_name="NURSEN", last_name="KORKMAZ", nationality="TUR",
                                              gender="F", document_no="A48I92506", document_type="I",
                                              birth_date="1999-10-22", expiry_date="2034-10-13"))],
    )
    rec = process_image(b"img", ocr_provider=FakeProvider(result), today=dt.date(2026, 10, 23))[0]
    f = rec.to_fields()
    assert (f["nationality"], f["sex"], f["passport_no"]) == ("TUR", "F", "A48I92506")
    assert Flag.FREE_TEXT_UNVERIFIED in rec.flags
    assert Flag.EXPIRED not in rec.flags
    assert not rec.is_green


def test_mrz_row_in_multi_result_is_green_and_fields_cross_checked():
    result = OcrResult(
        status="success", source="x", kind="passport_mrz",
        passengers=[_passenger(format="TD3", lines=[TD3_L1, TD3_L2],
                               fields=_fields(first_name="ANNA MARIA", last_name="ERIKSSON", document_no="L898902C3"))],
    )
    rec = process_image(b"img", ocr_provider=FakeProvider(result), today=TODAY)[0]
    assert rec.is_green and rec.mrz.checks["server_document_match"] is True

    bad = OcrResult(status="success", source="x", kind="passport_mrz",
                    passengers=[_passenger(format="TD3", lines=[TD3_L1, TD3_L2],
                                           fields=_fields(document_no="X9999"))])
    rec = process_image(b"img", ocr_provider=FakeProvider(bad), today=TODAY)[0]
    assert Flag.CHECKSUM_FAIL in rec.flags


def test_duplicates_within_one_list_are_flagged():
    row = _passenger(fields=_fields(first_name="A", last_name="B", nationality="ESP", gender="F", document_no="PAE933813"))
    result = OcrResult(status="success", source="x", kind="printed_list", passengers=[row, dict(row)])
    recs = process_image(b"img", ocr_provider=FakeProvider(result), today=TODAY)
    assert Flag.DUPLICATE not in recs[0].flags
    assert Flag.DUPLICATE in recs[1].flags


def test_empty_passengers_is_unreadable():
    result = OcrResult(status="success", source="x", kind="other", passengers=[], warnings=["no_passengers"])
    rec = process_image(b"img", ocr_provider=FakeProvider(result))[0]
    assert rec.mrz is None and Flag.UNREADABLE in rec.flags


def test_single_passenger_legacy_shape_still_works():
    """Eski sunucu: passengers yok, passenger + raw_text var."""
    result = OcrResult(status="success", source="google_vision", confidence="green",
                       passenger={"first_name": "ANNA MARIA", "last_name": "ERIKSSON", "nationality": "UTO",
                                  "gender": "F", "document_no": "L898902C3"},
                       raw_text=TD3_L1 + "\n" + TD3_L2)
    rec = to_records(result, provider_name="irtifa_server")[0]
    assert rec.mrz.checks_ok and rec.route == "irtifa_server"


# ─── ClaudeDirectProvider: yeni şema ────────────────────────────────────

class FakeAnthropic:
    def __init__(self, payload, stop_reason="end_turn"):
        self.payload, self.stop_reason, self.kwargs = payload, stop_reason, None
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(stop_reason=self.stop_reason,
                               content=[SimpleNamespace(type="text", text=json.dumps(self.payload))],
                               usage=SimpleNamespace(input_tokens=3000, output_tokens=900))


def test_claude_direct_parses_list_payload():
    payload = {
        "kind": "printed_list",
        "group": {"date": "2026-10-20", "hotel": "", "agency": "Aytorex", "booking_code": "AYTOREX-017-1",
                  "pax": 2, "nationality_hint": "POL", "note": ""},
        "passengers": [
            {"format": "NONE", "lines": [], "fields": _fields(first_name="Pawel", last_name="Jachymiak",
                                                              document_no="ew4480929", document_type="p",
                                                              birth_date="1987-10-12"),
             "confidence": 0.93, "annotation": "B", "selected": None},
            {"format": "NONE", "lines": [], "fields": _fields(first_name="Natalia", last_name="Jachymiak",
                                                              document_no="FB4939335", birth_date="2014-06-05"),
             "confidence": 0.6, "annotation": "", "selected": None},
        ],
        "confidence": 0.9,
    }
    client = FakeAnthropic(payload)
    result = ClaudeDirectProvider(client, "claude-sonnet-5-5").read(b"img", "image/jpeg")
    assert result.ok and result.kind == "printed_list"
    assert result.group["nationality_hint"] == "POL" and result.group["pax"] == 2
    assert [p["annotation"] for p in result.passengers] == ["B", ""]
    assert result.passengers[0]["fields"]["document_no"] == "ew4480929"
    assert result.passengers[0]["fields"]["document_type"] == "P"
    assert result.passengers[0]["confidence"] == "green" and result.passengers[1]["confidence"] == "red"
    assert client.kwargs["output_config"]["format"]["schema"]["required"] == ["kind", "group", "passengers", "confidence"]
    assert "tool_choice" not in client.kwargs

    recs = process_image(b"img", ocr_provider=ClaudeDirectProvider(client, "m"), today=TODAY)
    assert len(recs) == 2
    assert recs[0].mrz.nationality == "POL"           # grup ipucu uygulandı
    assert recs[0].to_fields()["passport_no"] == "EW4480929"
    assert recs[1].requires_manual_review            # düşük güven → manuel kontrol


def test_claude_direct_max_tokens_cut_is_reported():
    client = FakeAnthropic({"kind": "printed_list", "group": {}, "passengers": [], "confidence": 1}, stop_reason="max_tokens")
    result = ClaudeDirectProvider(client, "m").read(b"img", "image/jpeg")
    assert not result.ok and "kesildi" in result.error


# ─── IrtifaServerProvider: çok yolculu yanıt geçişi ─────────────────────

def test_server_multi_passenger_response_passes_through(monkeypatch):
    body = {"status": "success", "confidence": "green", "raw_text": "", "warnings": [], "source": "srv",
            "kind": "chat_message",
            "group": {"date": "2026-10-22", "hotel": "STONE HOUSE CAVE", "pax": 2, "agency": "", "booking_code": "",
                      "nationality_hint": "", "note": ""},
            "passengers": [_passenger(fields=_fields(first_name="A", last_name="B", nationality="KOR", gender="M",
                                                     document_no="M29647295", birth_date="1994-06-30")),
                           _passenger(fields=_fields(first_name="C", last_name="D", nationality="KOR", gender="F",
                                                     document_no="M498B8818", birth_date="1994-05-10"))]}

    class R:
        status_code = 200

        def json(self):
            return body

    monkeypatch.setattr("app.vision.irtifa_client.requests.post", lambda *a, **k: R())
    s = settings_mod.Settings(irtifa_license_key="LIC", irtifa_device_id="DEV")
    recs = process_image(b"img", settings=s, today=TODAY)
    assert len(recs) == 2 and recs[0].source_kind == "chat_message"
    assert recs[0].group["hotel"] == "STONE HOUSE CAVE" and recs[0].group["pax"] == 2


# ─── EXIF yön düzeltme ───────────────────────────────────────────────────

def test_prepare_image_applies_exif_rotation_and_caps_size():
    from PIL import Image

    im = Image.new("RGB", (3000, 1000), "white")
    buf = io.BytesIO()
    exif = Image.Exif()
    exif[0x0112] = 6   # Orientation: 90° CW döndür
    im.save(buf, format="JPEG", exif=exif)

    out_bytes, media = prepare_image(buf.getvalue(), "image/jpeg")
    out = Image.open(io.BytesIO(out_bytes))
    assert media == "image/jpeg"
    assert out.size[1] > out.size[0]            # dikey oldu
    assert max(out.size) <= 2000                # uzun kenar sınırlandı

    small = Image.new("RGB", (800, 600), "white")
    buf2 = io.BytesIO()
    small.save(buf2, format="PNG")
    same, media2 = prepare_image(buf2.getvalue(), "image/png")
    assert same == buf2.getvalue() and media2 == "image/png"   # değişiklik gerekmedi, dokunulmadı


def test_prepare_image_returns_input_on_garbage():
    assert prepare_image(b"not-an-image", "image/jpeg") == (b"not-an-image", "image/jpeg")
