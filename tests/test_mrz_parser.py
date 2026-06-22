"""MRZ parser + checksum testleri — ICAO 9303 referans örnekleriyle."""
from __future__ import annotations

import datetime as dt

from app.mrz.checksum import check_digit
from app.mrz.parser import parse, parse_td1, parse_td3

# ICAO 9303 Part 4 — TD3 (pasaport) referans örneği
TD3_L1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
TD3_L2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"

# ICAO 9303 Part 5 — TD1 (kimlik) referans örneği
TD1 = [
    "I<UTOD231458907<<<<<<<<<<<<<<<",
    "7408122F1204159UTO<<<<<<<<<<<6",
    "ERIKSSON<<ANNA<MARIA<<<<<<<<<<",
]


def test_check_digit_known_values():
    # ICAO 9303 örnek: "D23145890734" -> check 7 (belge no alanı)
    assert check_digit("D23145890") == 7
    assert check_digit("740812") == 2
    assert check_digit("120415") == 9


def test_td3_fields_and_checksums():
    r = parse_td3(TD3_L1, TD3_L2)
    assert r.format == "TD3"
    assert r.issuing_country == "UTO"
    assert r.nationality == "UTO"
    assert r.document_number == "L898902C3"
    assert r.sex == "F"
    assert r.surname == "ERIKSSON"
    assert r.given_names == "ANNA MARIA"
    assert r.name == "ANNA MARIA ERIKSSON"
    assert r.birth_date == dt.date(1974, 8, 12)
    assert r.expiry_date == dt.date(2012, 4, 15)
    # tüm check digit'ler geçerli specimen
    assert r.checks_ok, r.checks


def test_td1_fields_and_checksums():
    r = parse_td1(*TD1)
    assert r.format == "TD1"
    assert r.nationality == "UTO"
    assert r.document_number == "D23145890"
    assert r.sex == "F"
    assert r.surname == "ERIKSSON"
    assert r.given_names == "ANNA MARIA"
    assert r.birth_date == dt.date(1974, 8, 12)
    assert r.expiry_date == dt.date(2012, 4, 15)
    assert r.checks_ok, r.checks


def test_parse_dispatch_by_line_count():
    assert parse([TD3_L1, TD3_L2]).format == "TD3"
    assert parse(TD1).format == "TD1"


def test_checksum_fail_detected():
    # belge no check digit'ini boz: "...C36" -> "...C35"
    bad_l2 = TD3_L2[:9] + "5" + TD3_L2[10:]
    r = parse_td3(TD3_L1, bad_l2)
    assert not r.checks["document_number"]
    assert not r.checks_ok


def test_real_passport_number_carried_verbatim():
    # alfanümerik belge no harf içerebilir (planlama/manifesto aynen taşır)
    r = parse_td3(TD3_L1, TD3_L2)
    assert any(c.isalpha() for c in r.document_number)
