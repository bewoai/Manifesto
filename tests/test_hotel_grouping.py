"""Otel gruplaması: aynı otelden gelen rezervasyonlar aynı balona (pickup kolaylığı).

Fixture `seat_template_ekim.xlsx` (PII'siz) 22.10.2026: BZV 24 (4 boş), BYJ 24 (4 boş),
BZR 22 (6 boş), BYF bandı tamamen boş (28). OTEL 36 → BZR (15), OTEL 34 → BYJ (4),
OTEL 24 → BZV (5). Sayfada 2+ balona dağılmış otel yok.
"""
from __future__ import annotations

import importlib
import shutil
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.manifest.excel_cache import clear_excel_cache
from app.manifest.planning import (
    PassengerIdentity, ReservationBlock, assign_balloon, balloon_load, choose_balloon,
    create_reservation, hotel_seats_by_balloon, hotel_split, read_blocks, read_rows,
)
from app.textfold import fold_name

FIXTURE = Path(__file__).parent / "fixtures" / "seat_template_ekim.xlsx"
PARTIAL = "22.10.2026"
CODES = ["BYF", "BTK", "BYJ", "BZR", "BZV"]
DAY = "02.11.2026"


def _fresh(p, sheet):
    clear_excel_cache()
    return read_rows(p, sheet), read_blocks(p, sheet)


def _caps(mapping: dict, default: int = 28):
    return lambda code: mapping.get(code, default)


def _append_wb(tmp_path, groups) -> Path:
    """Ekleme şablonu: groups = [(balon, pax, otel), ...] sırayla eklenir."""
    p = tmp_path / "hotels.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = DAY
    wb.save(p)
    clear_excel_cache()
    for balloon, pax, hotel in groups:
        create_reservation(p, DAY, pax=pax, balloon=balloon, fields={"agency": "ACENTE X", "hotel": hotel})
    clear_excel_cache()
    return p


@pytest.fixture()
def seat_wb(tmp_path):
    p = tmp_path / "ekim.xlsx"
    shutil.copy2(FIXTURE, p)
    clear_excel_cache()
    return p


def _block(lead_row, balloon, pax, hotel) -> ReservationBlock:
    return ReservationBlock(
        lead_row=lead_row, rows=[lead_row + i for i in range(pax)], pax=pax, room="", agency="A",
        reserved_by="", company="THK", balloon=balloon, pilot="", note="", driver="", coming_place="",
        hotel=hotel, pickup="", lead_name="",
        passengers=[PassengerIdentity(row=lead_row + i, nationality="", sex="", name="", passport_no="")
                    for i in range(pax)],
    )


# ─── Katlama ve otel → balon eşlemesi ────────────────────────────────────

def test_fold_name_hotel_spellings():
    assert fold_name("ARGOS") == fold_name("Argos") == fold_name(" argos ")
    assert fold_name("Kapadokya Otel") == fold_name("KAPADOKYA OTEL") == fold_name("kapadokya   otel")
    assert fold_name("Şirince İz Otel") == fold_name("SIRINCE IZ OTEL") == fold_name("şirince iz otel")


def test_hotel_seats_by_balloon_orders_most_seats_first():
    blocks = [_block(4, "BTK", 2, "Argos"), _block(6, "BZR", 6, "ARGOS"), _block(12, "BTK", 1, "argos"),
              _block(13, "BYF", 9, "OTEL A"), _block(22, "", 2, "ARGOS")]
    assert list(hotel_seats_by_balloon(blocks, "ARGOS").items()) == [("BZR", 6), ("BTK", 3)]
    assert hotel_seats_by_balloon(blocks, "") == {}
    assert hotel_seats_by_balloon(blocks, "YOK OTEL") == {}


# ─── Ekleme şablonu (append) ─────────────────────────────────────────────

def test_affinity_picks_hotels_balloon(tmp_path):
    p = _append_wb(tmp_path, [("BYF", 10, "OTEL A"), ("BTK", 2, "ARGOS"), ("BZR", 6, "ARGOS")])
    rows, blocks = _fresh(p, DAY)
    # otel yokken first-fit → BYF
    assert choose_balloon(rows, blocks, 3, CODES, 28) == {
        "balloon": "BYF", "overflow": False, "mode": "append", "hotel_match": False}
    # ARGOS en çok BZR'de (6) → BZR; normal sıradaki BYF ve BTK'nın önüne geçer
    assert choose_balloon(rows, blocks, 3, CODES, 28, hotel="ARGOS") == {
        "balloon": "BZR", "overflow": False, "mode": "append", "hotel_match": True}
    # yeni otel → normal davranış
    res = choose_balloon(rows, blocks, 3, CODES, 28, hotel="YENİ OTEL")
    assert (res["balloon"], res["hotel_match"]) == ("BYF", False)
    # assign_balloon (ekleme modu) oteli doğrudan alır; tercih için bloklar gerekir
    load = balloon_load(blocks)
    assert assign_balloon(load, 3, CODES, 28, hotel="argos", blocks=blocks) == ("BZR", False)
    assert assign_balloon(load, 3, CODES, 28, hotel="argos") == ("BYF", False)   # blocks yok → tercih yok


@pytest.mark.parametrize("given,stored", [
    ("Argos", "ARGOS"), ("ARGOS", "Argos"),
    ("Kapadokya Otel", "KAPADOKYA OTEL"), ("KAPADOKYA OTEL", "kapadokya  otel"),
    ("şirince iz otel", "ŞİRİNCE İZ OTEL"),
])
def test_affinity_turkish_insensitive(tmp_path, given, stored):
    p = _append_wb(tmp_path, [("BYF", 10, "OTEL A"), ("BYJ", 4, stored)])
    rows, blocks = _fresh(p, DAY)
    res = choose_balloon(rows, blocks, 2, CODES, 28, hotel=given)
    assert (res["balloon"], res["hotel_match"]) == ("BYJ", True)


def test_capacity_full_falls_back(tmp_path):
    p = _append_wb(tmp_path, [("BYF", 10, "OTEL A"), ("BZR", 26, "ARGOS")])
    rows, blocks = _fresh(p, DAY)
    # BZR 26 + 3 > 28 → otel tercihi düşer, normal first-fit
    res = choose_balloon(rows, blocks, 3, CODES, 28, hotel="ARGOS")
    assert res == {"balloon": "BYF", "overflow": False, "mode": "append", "hotel_match": False}
    # balon başına kapasite: BZR 30 → sığar
    res = choose_balloon(rows, blocks, 3, CODES, _caps({"BZR": 30}), hotel="ARGOS")
    assert (res["balloon"], res["hotel_match"]) == ("BZR", True)
    # 2 kişi tam sığar (26 + 2 = 28)
    assert choose_balloon(rows, blocks, 2, CODES, 28, hotel="ARGOS")["balloon"] == "BZR"


def test_daily_limit_respected(tmp_path):
    p = _append_wb(tmp_path, [("BYF", 27, "OTEL A"), ("BZR", 26, "ARGOS"), ("BYJ", 10, "OTEL B")])
    rows, blocks = _fresh(p, DAY)
    flying = {"BYF", "BZR", "BYJ"}
    # sınır yokken: BZR dolu → ilk boş yer BTK (yeni balon)
    assert choose_balloon(rows, blocks, 3, CODES, 28, hotel="ARGOS")["balloon"] == "BTK"
    # sınır dolu: otel balonu dolu → yalnız uçan balonlar → BYJ, yeni balon açılmaz
    res = choose_balloon(rows, blocks, 3, CODES, 28, allowed=flying, hotel="ARGOS")
    assert res == {"balloon": "BYJ", "overflow": False, "mode": "append", "hotel_match": False}
    # otelin balonu izinli değilse tercih edilmez
    res = choose_balloon(rows, blocks, 2, CODES, 28, allowed={"BYF", "BYJ"}, hotel="ARGOS")
    assert (res["balloon"], res["hotel_match"]) == ("BYJ", False)


# ─── Koltuk şablonu (seat) ───────────────────────────────────────────────

def test_seat_template_affinity(seat_wb):
    rows, blocks = _fresh(seat_wb, PARTIAL)
    # otel yokken boş BYF bandı
    assert choose_balloon(rows, blocks, 3, CODES, 28)["balloon"] == "BYF"
    # OTEL 36 BZR'de; BZR'de 6 ardışık boş koltuk → BZR
    assert choose_balloon(rows, blocks, 3, CODES, 28, hotel="otel 36") == {
        "balloon": "BZR", "overflow": False, "mode": "seat", "hotel_match": True}
    # 7 kişi BZR'nin 6 ardışık koltuğuna sığmaz → normal sıra (BYF)
    assert choose_balloon(rows, blocks, 7, CODES, 28, hotel="OTEL 36") == {
        "balloon": "BYF", "overflow": False, "mode": "seat", "hotel_match": False}
    # OTEL 34 BYJ'de (4 boş): 4 sığar, 5 sığmaz
    assert choose_balloon(rows, blocks, 4, CODES, 28, hotel="Otel 34")["balloon"] == "BYJ"
    assert choose_balloon(rows, blocks, 5, CODES, 28, hotel="Otel 34")["balloon"] == "BYF"
    # balon kapasitesi: BZR 24 → 22 + 3 aşar → BYF
    res = choose_balloon(rows, blocks, 3, CODES, _caps({"BZR": 24}), hotel="OTEL 36")
    assert (res["balloon"], res["hotel_match"]) == ("BYF", False)
    # günlük sınır: uçan balonlar içinde otel balonu önce
    flying = {"BZV", "BYJ", "BZR"}
    assert choose_balloon(rows, blocks, 2, CODES, 28, allowed=flying)["balloon"] == "BYJ"
    assert choose_balloon(rows, blocks, 2, CODES, 28, allowed=flying, hotel="OTEL 36")["balloon"] == "BZR"
    # istenen balon otel tercihinin önünde
    res = choose_balloon(rows, blocks, 2, CODES, 28, requested="BYJ", hotel="OTEL 36")
    assert (res["balloon"], res["hotel_match"]) == ("BYJ", False)


# ─── hotel_split ─────────────────────────────────────────────────────────

def test_hotel_split_lists_spread_hotels():
    blocks = [_block(4, "BTK", 2, "Argos"), _block(6, "BZR", 6, "ARGOS"), _block(12, "BYF", 9, "OTEL A"),
              _block(21, "BYF", 3, "Kapadokya Otel"), _block(24, "BYJ", 4, "KAPADOKYA OTEL"),
              _block(28, "BYJ", 1, "Kapadokya  otel"), _block(29, "BYF", 2, ""), _block(31, "BZV", 2, "")]
    assert hotel_split(blocks) == [
        {"hotel": "Argos", "balloons": ["BZR", "BTK"], "seats": 8},
        {"hotel": "Kapadokya Otel", "balloons": ["BYJ", "BYF"], "seats": 8},
    ]


def test_hotel_split_empty_on_fixture(seat_wb):
    _, blocks = _fresh(seat_wb, PARTIAL)
    assert hotel_split(blocks) == []


# ─── API ─────────────────────────────────────────────────────────────────

def _make_client(tmp_path, monkeypatch, planning: Path, **settings_fields):
    monkeypatch.setenv("MANIFESTO_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.setenv("IRTIFA_DB_PATH", str(tmp_path / "rules.db"))
    import app.settings as settings_mod
    importlib.reload(settings_mod)
    import app.main as main_mod
    importlib.reload(main_mod)
    c = TestClient(main_mod.app)
    c.post("/api/auth/setup", json={"username": "admin", "display_name": "Y", "password": "strong-pass"})
    s = settings_mod.load()
    s.planning_xlsx = str(planning)
    s.balloon_codes = list(CODES)
    s.is_setup_complete = True
    for key, value in settings_fields.items():
        setattr(s, key, value)
    settings_mod.save(s.normalized())
    return c


def _create(client, sheet, endpoint, **body):
    load = client.get("/api/planning/load", params={"sheet": sheet}).json()
    payload = {"sheet": sheet, "expected_revision": load["workbook_revision"], **body}
    if endpoint.endswith("create-with-identities"):
        payload.setdefault("identities", [])
    return client.post(endpoint, json=payload)


@pytest.mark.parametrize("endpoint", ["/api/planning/create-block", "/api/planning/create-with-identities"])
def test_api_hotel_match_in_response(tmp_path, monkeypatch, seat_wb, endpoint):
    c = _make_client(tmp_path, monkeypatch, seat_wb)
    r = _create(c, PARTIAL, endpoint, pax=3, hotel="otel 36", agency="ACENTE Y")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["balloon"] == "BZR"
    assert body["hotel_match"] is True
    assert body["message"].endswith(" otel 36 otelinin diğer yolcularıyla aynı balona (BZR) atandı.")

    r = _create(c, PARTIAL, endpoint, pax=3, hotel="YENİ OTEL", agency="ACENTE Y")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["balloon"], body["hotel_match"]) == ("BYF", False)
    assert "otelinin" not in body["message"]


def test_api_load_hotel_split(tmp_path, monkeypatch, seat_wb):
    c = _make_client(tmp_path, monkeypatch, seat_wb)
    assert c.get("/api/planning/load", params={"sheet": PARTIAL}).json()["hotel_split"] == []
    # OTEL 24 BZV'de (5 kişi, 4 boş koltuk): 6 kişi sığmaz → BYF → otel iki balona dağılır
    r = _create(c, PARTIAL, "/api/planning/create-block", pax=6, hotel="Otel 24", agency="ACENTE Y")
    assert r.status_code == 200, r.text
    assert (r.json()["balloon"], r.json()["hotel_match"]) == ("BYF", False)
    load = c.get("/api/planning/load", params={"sheet": PARTIAL}).json()
    assert load["hotel_split"] == [{"hotel": "OTEL 24", "balloons": ["BYF", "BZV"], "seats": 11}]
    # öneri readiness uyarısı değildir
    assert not any("hotel" in i["code"] for i in load["readiness"]["issues"])
