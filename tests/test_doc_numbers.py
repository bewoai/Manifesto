"""Belge numarasından uyruk tespiti: kontrol haneleri, biçimler, listede çoğunluk."""
from __future__ import annotations

import datetime as dt

from app.country.doc_numbers import (
    guess_from_document, infer_nationalities, valid_es_dni, valid_pl_id_card, valid_tr_tckn,
)
from app.mrz.parser import MRZResult
from app.validation.flags import Flag
from app.vision.extractor import process_image
from app.vision.providers import OcrResult

# Sentetik ama geçerli örnekler (gerçek kişiye ait değil)
ES_DNI = "12345678Z"        # 12345678 % 23 = 14 → Z
PL_ID = "ABA300000"         # Polonya kimlik kartı standart örneği (kontrol hanesi 3)
TR_TCKN = "10000000146"     # geçerli T.C. kimlik no test değeri


def test_checksum_validators():
    assert valid_es_dni(ES_DNI) and not valid_es_dni("12345678A")
    assert valid_pl_id_card(PL_ID) and not valid_pl_id_card("ABA400000")
    assert valid_tr_tckn(TR_TCKN) and not valid_tr_tckn("10000000147") and not valid_tr_tckn("01234567890")


def test_guess_certain_and_pattern():
    g = guess_from_document(ES_DNI)
    assert g.certain and g.candidates == ("ESP",)
    g = guess_from_document(PL_ID)
    assert g.certain and g.candidates == ("POL",)
    g = guess_from_document(TR_TCKN)
    assert g.certain and g.candidates == ("TUR",)

    assert guess_from_document("PAE123456").candidates == ("ESP",) and not guess_from_document("PAE123456").certain
    assert guess_from_document("CA12345AB").candidates == ("ITA",)
    assert guess_from_document("YB1234567").candidates[0] == "ITA"
    assert guess_from_document("M123A4567").candidates == ("KOR",)
    assert guess_from_document("A12B34567").candidates == ("TUR",)
    assert set(guess_from_document("EW1234567").candidates) >= {"POL", "AUS"}
    assert set(guess_from_document("123456789").candidates) == {"GBR", "USA"}
    assert guess_from_document("") is None
    assert guess_from_document("?!") is None
    assert guess_from_document("ZZZZZZZZZZZZ") is None


class _Row:
    def __init__(self, doc, nat="", source=""):
        self.mrz = MRZResult("LIST", "P", nat, nat, doc, "F", "X", "Y", None, None, checks={}, raw_lines=[])
        self.document_type = ""
        self.nationality_source = source if nat else ""
        self.nationality_reason = ""


def test_infer_fills_from_checksum_and_list_majority():
    # Polonya listesi: kimlik kartları kesin POL, pasaportlar (2 harf + 7 hane) çok adaylı → çoğunluk POL
    rows = [_Row(PL_ID), _Row(PL_ID), _Row("EW1234567"), _Row("FB7654321")]
    infer_nationalities(rows)
    assert [r.mrz.nationality for r in rows] == ["POL"] * 4
    assert [r.nationality_source for r in rows] == ["document", "document", "list", "list"]


def test_infer_spanish_list_mixed_dni_and_passport():
    rows = [_Row(ES_DNI), _Row("PAE123456"), _Row("XDE654321")]
    infer_nationalities(rows)
    assert [r.mrz.nationality for r in rows] == ["ESP"] * 3
    assert rows[0].nationality_source == "document" and rows[1].nationality_source == "pattern"


def test_infer_respects_stated_and_uses_model_guess_last():
    rows = [_Row("12345", "GBR", "stated"), _Row("ZZZ"), _Row("QQQ")]
    infer_nationalities(rows, model_guess="rou")
    assert rows[0].mrz.nationality == "GBR"                    # yazanına dokunulmaz
    # 1 bilinen satır güçlü çoğunluk için yetmez (<3) → model tahmini
    assert [r.mrz.nationality for r in rows[1:]] == ["ROU", "ROU"]
    assert all(r.nationality_source == "model" for r in rows[1:])


def test_infer_strong_majority_fills_unrecognised_formats():
    rows = [_Row("1", "ITA", "stated"), _Row("2", "ITA", "stated"), _Row("3", "ITA", "stated"), _Row("??")]
    infer_nationalities(rows)
    assert rows[3].mrz.nationality == "ITA" and rows[3].nationality_source == "list"


def test_certain_checksum_overrides_header_hint():
    r = _Row(TR_TCKN, "ITA", "header")       # İtalyan grubunda T.C. kimlikli rehber
    infer_nationalities([r])
    assert r.mrz.nationality == "TUR" and r.nationality_source == "document"


def _fields(**kw):
    base = {"first_name": "", "last_name": "", "nationality": "", "gender": "", "document_no": "",
            "document_type": "", "birth_date": "", "expiry_date": ""}
    base.update(kw)
    return base


def test_end_to_end_flags_and_fields():
    result = OcrResult(
        status="success", source="x", kind="printed_list",
        group={"nationality_hint": "", "nationality_guess": "ROU", "hotel": "", "agency": "", "date": "",
               "booking_code": "", "pax": None, "note": ""},
        passengers=[
            {"format": "NONE", "lines": [], "fields": _fields(first_name="A", last_name="B", gender="F", document_no=ES_DNI),
             "confidence": 0.95, "annotation": "", "selected": None},
            {"format": "NONE", "lines": [], "fields": _fields(first_name="C", last_name="D", gender="M", document_no="12345"),
             "confidence": 0.95, "annotation": "", "selected": None},
        ],
    )

    class P:
        name = "fake"

        def read(self, b, m):
            return result

    recs = process_image(b"img", ocr_provider=P(), today=dt.date(2026, 10, 23))
    f0, f1 = recs[0].to_fields(), recs[1].to_fields()
    assert f0["nationality"] == "ESP" and f0["nationality_source"] == "document"
    assert Flag.NATIONALITY_INFERRED not in recs[0].flags          # kesin → bayrak yok
    assert Flag.MISSING_REQUIRED_FIELDS not in recs[0].flags
    assert f1["nationality"] == "ROU" and f1["nationality_source"] == "model"
    assert Flag.NATIONALITY_INFERRED in recs[1].flags              # tahmin → operatör baksın
    assert not recs[0].is_green and not recs[1].is_green           # MRZ'siz → yine sarı
