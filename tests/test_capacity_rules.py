"""Kapasite kuralları: balon başına kapasite, günlük balon sınırı, acente kotası.

Fixture `seat_template_ekim.xlsx` (PII'siz) 22.10.2026: BZV 24 (4 boş), BYJ 24 (4 boş),
BZR 22 (6 boş), BYF bandı tamamen boş (28). Uçan balon sayısı 3. ACENTE 8 = 26 koltuk.
"""
from __future__ import annotations

import importlib
import shutil
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app import config
from app.manifest.excel_cache import clear_excel_cache
from app.manifest.planning import (
    ReservationBlock, assign_balloon, choose_balloon, create_reservation, read_blocks, read_rows,
)
from app.readiness import check_blocks, check_workbook
from app.settings import Settings, fold_agency

FIXTURE = Path(__file__).parent / "fixtures" / "seat_template_ekim.xlsx"
PARTIAL, SPARSE = "22.10.2026", "23.10.2026"
CODES = ["BYF", "BTK", "BYJ", "BZR", "BZV"]
APPEND_DAY = "01.11.2026"


@pytest.fixture()
def wb_path(tmp_path):
    p = tmp_path / "ekim.xlsx"
    shutil.copy2(FIXTURE, p)
    clear_excel_cache()
    return p


def _fresh(p, sheet):
    clear_excel_cache()
    return read_rows(p, sheet), read_blocks(p, sheet)


def _caps(mapping: dict, default: int = 28):
    return lambda code: mapping.get(code, default)


@pytest.fixture()
def append_wb(tmp_path):
    """Ekleme şablonu: BYF 28 (dolu), BTK/BYJ/BZR 20'şer → 4 balon uçuyor, BZV boş."""
    p = tmp_path / "append.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = APPEND_DAY
    wb.save(p)
    clear_excel_cache()
    for balloon, pax in (("BYF", 28), ("BTK", 20), ("BYJ", 20), ("BZR", 20)):
        create_reservation(p, APPEND_DAY, pax=pax, balloon=balloon,
                           fields={"agency": "Bedel Turizm" if balloon == "BTK" else "ACENTE X"})
    clear_excel_cache()
    return p


def _block(lead_row=4, *, lead_name="", agency="", balloon="BYF", pax=1, **kw) -> ReservationBlock:
    from app.manifest.planning import PassengerIdentity

    base = dict(room="", reserved_by="", company="THK", pilot="P", note="", driver="1",
                coming_place="DİREKT ALAN", hotel="OTEL", pickup="05:00")
    base.update(kw)
    return ReservationBlock(
        lead_row=lead_row, rows=[lead_row + i for i in range(pax)], pax=pax, agency=agency,
        balloon=balloon, lead_name=lead_name,
        passengers=[PassengerIdentity(row=lead_row + i, nationality="TUR", sex="M",
                                      name=lead_name if i == 0 else f"YOLCU {i}", passport_no=f"U{lead_row}{i}")
                    for i in range(pax)],
        **base,
    )


# ─── Acente adı katlama ──────────────────────────────────────────────────

def test_fold_agency_ignores_turkish_letters_case_and_spaces():
    assert fold_agency("Bedel Turizm") == fold_agency("BEDEL TURİZM") == fold_agency("bedel  turizm ") == "BEDEL TURIZM"
    assert fold_agency("çağ ışık özgür şüheda") == "CAG ISIK OZGUR SUHEDA"
    assert fold_agency("ÇAĞ IŞIK ÖZGÜR ŞÜHEDA") == "CAG ISIK OZGUR SUHEDA"




# ─── Balon başına kapasite ───────────────────────────────────────────────

def test_assign_balloon_uses_per_balloon_capacity():
    load = {"A": 20, "B": 0}
    assert assign_balloon(load, 9, ["A", "B"], 28) == ("B", False)                    # A: 8 boş
    assert assign_balloon(load, 9, ["A", "B"], _caps({"A": 30, "B": 10})) == ("A", False)
    assert assign_balloon(load, 11, ["A", "B"], _caps({"A": 30, "B": 10})) == ("A", True)   # en çok boş yer A (10)


def test_choose_balloon_seat_mode_respects_per_balloon_capacity(wb_path):
    rows, blocks = _fresh(wb_path, PARTIAL)
    flying = {"BZV", "BYJ", "BZR"}
    # BYJ 24 + 4 = 28 ≤ 28 → BYJ
    assert choose_balloon(rows, blocks, 4, CODES, 28, allowed=flying)["balloon"] == "BYJ"
    # BYJ kapasitesi 26 → 24 + 4 aşar → sonraki uygun balon BZR (22 + 4 ≤ 28, 6 ardışık koltuk)
    res = choose_balloon(rows, blocks, 4, CODES, _caps({"BYJ": 26}), allowed=flying)
    assert res == {"balloon": "BZR", "overflow": False, "mode": "seat",
                   "hotel_match": False}


def test_choose_balloon_append_mode_per_balloon_capacity(append_wb):
    rows, blocks = _fresh(append_wb, APPEND_DAY)
    # 9 kişi: varsayılan 28'de uçan balonların hiçbirinde yer yok → boş BZV
    assert choose_balloon(rows, blocks, 9, CODES, 28) == {"balloon": "BZV", "overflow": False, "mode": "append",
        "hotel_match": False}
    # BTK kapasitesi 30 → 20 + 9 sığar
    assert choose_balloon(rows, blocks, 9, CODES, _caps({"BTK": 30}))["balloon"] == "BTK"


# ─── Günlük balon sınırı ─────────────────────────────────────────────────

def test_daily_limit_blocks_fifth_balloon_and_allows_in_use(append_wb):
    rows, blocks = _fresh(append_wb, APPEND_DAY)
    flying = {"BYF", "BTK", "BYJ", "BZR"}
    # 5 kişi uçan bir balona sığar → BTK
    assert choose_balloon(rows, blocks, 5, CODES, 28, allowed=flying) == {
        "balloon": "BTK", "overflow": False, "mode": "append", "hotel_match": False}
    # 9 kişi: uçan balonlarda yer yok; 5. balon (BZV) yasak → overflow
    res = choose_balloon(rows, blocks, 9, CODES, 28, allowed=flying)
    assert res["overflow"] is True and res["balloon"] in flying


def test_daily_limit_in_seat_mode(wb_path):
    rows, blocks = _fresh(wb_path, PARTIAL)
    flying = {"BZV", "BYJ", "BZR"}
    assert choose_balloon(rows, blocks, 2, CODES, 28)["balloon"] == "BYF"              # sınır yokken boş bant
    assert choose_balloon(rows, blocks, 2, CODES, 28, allowed=flying)["balloon"] == "BYJ"
    assert choose_balloon(rows, blocks, 5, CODES, 28, allowed=flying)["balloon"] == "BZR"
    res = choose_balloon(rows, blocks, 7, CODES, 28, allowed=flying)
    assert res["overflow"] is True and res["mode"] == "seat"


# ─── Readiness ───────────────────────────────────────────────────────────

def test_readiness_per_balloon_capacity_and_daily_limit(wb_path):
    clear_excel_cache()
    base = check_workbook(wb_path, PARTIAL, balloon_capacity=28)
    assert not any(i["code"] in ("capacity_overflow", "daily_balloon_limit")
                   for i in base["issues"])
    assert base["balloons_in_use"] == 3

    r = check_workbook(wb_path, PARTIAL, balloon_capacity=_caps({"BZV": 20}),
                       daily_max_balloons=2)
    by_code = {}
    for issue in r["issues"]:
        by_code.setdefault(issue["code"], []).append(issue)
    over = by_code["capacity_overflow"]
    assert [(i["balloon"], i["message"]) for i in over] == [("BZV", "BZV kapasitesi aşıldı: 24/20.")]
    assert by_code["daily_balloon_limit"][0]["message"] == "Günlük balon sınırı aşıldı: 3/2 balon."
    assert "agency_quota_exceeded" not in by_code   # acente kotası yok
    # sınır tam doluyken uyarı yok (yalnız aşınca)
    assert "daily_balloon_limit" not in check_workbook(wb_path, PARTIAL, daily_max_balloons=3)["counts"]


def test_readiness_issues_carry_lead_name_and_named_messages():
    named = _block(83, lead_name="AHMET YILMAZ", pickup="", pax=2)
    named.passengers[1].passport_no = ""
    anon = _block(90, lead_name="", hotel="", pax=1)
    anon.pax = 2   # PAX uyuşmazlığı
    r = check_blocks([named, anon], balloon_capacity=28)
    for issue in r["issues"]:
        if "lead_row" in issue:
            assert "lead_name" in issue, issue
    msgs = {(i["code"], i.get("row", i.get("lead_row"))): i["message"] for i in r["issues"]}
    assert msgs[("missing_pickup", 83)] == "Satır 83 · AHMET YILMAZ: pickup eksik."
    assert msgs[("missing_identity", 84)] == "Satır 84 · YOLCU 1: pasaport/kimlik no eksik."
    assert msgs[("missing_hotel", 90)] == "Satır 90: otel eksik."
    assert msgs[("pax_mismatch", 90)] == "Satır 90: PAX 2, yolcu satırı 1."
    pickup = next(i for i in r["issues"] if i["code"] == "missing_pickup")
    assert pickup["lead_row"] == 83 and pickup["lead_name"] == "AHMET YILMAZ"


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


def _create(client, sheet, endpoint="/api/planning/create-block", **body):
    load = client.get("/api/planning/load", params={"sheet": sheet}).json()
    payload = {"sheet": sheet, "hotel": "OTEL 9", "expected_revision": load["workbook_revision"], **body}
    if endpoint.endswith("create-with-identities"):
        payload.setdefault("identities", [])
    return client.post(endpoint, json=payload)


def test_api_load_exposes_capacity_rules(tmp_path, monkeypatch, wb_path):
    c = _make_client(tmp_path, monkeypatch, wb_path, balloon_capacities={"bzr": 24},
                     daily_max_balloons=4)
    body = c.get("/api/planning/load", params={"sheet": PARTIAL}).json()
    assert body["capacity"] == 28
    assert body["capacities"] == {"BYF": 28, "BTK": 28, "BYJ": 28, "BZR": 24, "BZV": 28}
    assert body["daily_max_balloons"] == 4
    assert body["balloons_in_use"] == 3
    assert "agency_usage" not in body
    # sayfada görülen ama Ayarlar'da olmayan balon da kapasite listesinde
    sparse = c.get("/api/planning/load", params={"sheet": SPARSE}).json()
    assert sparse["capacities"]["BZK"] == 28
    # readiness balon başına kapasiteyi kullanır: BZR 22/24 → aşım yok
    assert "capacity_overflow" not in body["readiness"]["counts"]


def test_api_daily_limit_409_message_and_override(tmp_path, monkeypatch, wb_path):
    c = _make_client(tmp_path, monkeypatch, wb_path, daily_max_balloons=3)
    # uçan balona sığan grup → oraya gider (BYF bandı boş olsa da)
    ok = _create(c, PARTIAL, pax=2)
    assert ok.status_code == 200, ok.text
    assert ok.json()["balloon"] == "BYJ"

    r = _create(c, PARTIAL, pax=7)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "capacity_confirmation_required"
    assert d["message"].startswith("Günlük balon sınırı (3) dolu; yalnız uçan balonlara eklenebilir")
    assert d["daily_max_balloons"] == 3
    assert d["capacities"] == {code: 28 for code in CODES}

    # onaylı override yeni balona izin verir; readiness sınır aşımını işaretler
    r = _create(c, PARTIAL, pax=7, allow_overflow=True, requested_balloon="BYF")
    assert r.status_code == 200, r.text
    assert r.json()["balloon"] == "BYF"
    load = c.get("/api/planning/load", params={"sheet": PARTIAL}).json()
    assert load["balloons_in_use"] == 4
    issue = next(i for i in load["readiness"]["issues"] if i["code"] == "daily_balloon_limit")
    assert issue["message"] == "Günlük balon sınırı aşıldı: 4/3 balon."


def test_api_daily_limit_append_mode_blocks_fifth_balloon(tmp_path, monkeypatch, append_wb):
    c = _make_client(tmp_path, monkeypatch, append_wb, daily_max_balloons=4)
    r = _create(c, APPEND_DAY, pax=9, agency="ACENTE Y")
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["message"].startswith("Günlük balon sınırı (4) dolu")
    ok = _create(c, APPEND_DAY, pax=5, agency="ACENTE Y")
    assert ok.status_code == 200, ok.text
    assert ok.json()["balloon"] == "BTK"


def test_api_capacity_409_without_daily_limit_has_new_fields(tmp_path, monkeypatch, wb_path):
    c = _make_client(tmp_path, monkeypatch, wb_path, balloon_capacities={"BYF": 6})
    # BYF kapasitesi 6: 7 kişi hiçbir balona sığmaz (diğerlerinde en uzun dizi 6)
    r = _create(c, PARTIAL, pax=7)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "capacity_confirmation_required"
    assert d["daily_max_balloons"] == 0
    assert d["capacities"]["BYF"] == 6
    assert not d["message"].startswith("Günlük")




def test_readiness_flags_daily_capacity():
    blocks = [_block(4, pax=2, balloon="BYF"), _block(10, pax=2, balloon="BYJ")]
    assert "daily_capacity_exceeded" not in check_blocks(blocks, daily_capacity=4)["counts"]
    r = check_blocks(blocks, daily_capacity=3)
    issue = next(i for i in r["issues"] if i["code"] == "daily_capacity_exceeded")
    assert issue["message"] == "Günlük kapasite aşıldı: 4/3 kişi."


def test_api_daily_capacity_409_and_override(tmp_path, monkeypatch, append_wb):
    # append_wb: 28 + 20 + 20 + 20 = 88 kişi
    c = _make_client(tmp_path, monkeypatch, append_wb, daily_capacity=90)
    load = c.get("/api/planning/load", params={"sheet": APPEND_DAY}).json()
    assert load["daily_capacity"] == 90
    r = _create(c, APPEND_DAY, pax=3, agency="ACENTE Y")
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "daily_capacity_exceeded" and (d["used"], d["pax"], d["capacity"]) == (88, 3, 90)
    r = _create(c, APPEND_DAY, endpoint="/api/planning/create-with-identities", pax=3, agency="ACENTE Y")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "daily_capacity_exceeded"
    ok = _create(c, APPEND_DAY, pax=2, agency="ACENTE Y")
    assert ok.status_code == 200, ok.text
    over = _create(c, APPEND_DAY, pax=3, agency="ACENTE Y", allow_daily_capacity_override=True)
    assert over.status_code == 200, over.text
    load = c.get("/api/planning/load", params={"sheet": APPEND_DAY}).json()
    assert load["readiness"]["counts"].get("daily_capacity_exceeded") == 1
