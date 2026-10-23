"""Koltuk şablonu: günün satırları önceden balonlara dağıtılmış (gerçek Ekim planlaması).

Fixture `tests/fixtures/seat_template_ekim.xlsx`: gerçek dosyanın 21/22/23 Ekim sayfaları,
isim/pasaport/otel/acente/pilot/oda/not sentetik değerlerle maskelenmiş (PII yok);
düzen, birleşmeler, balon bantları ve PAX'lar korunmuş.
  21.10 tam dolu · 22.10 kısmen dolu (BYF bandı tamamen boş) · 23.10 az dolu
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
    choose_balloon, create_reservation, delete_passenger_from_reservation, delete_reservation,
    free_seat_runs, free_seat_summary, read_blocks, read_rows, resize_reservation, write_identity,
)
from app.manifest.writer import build_rows
from app.readiness import check_workbook

FIXTURE = Path(__file__).parent / "fixtures" / "seat_template_ekim.xlsx"
FULL, PARTIAL, SPARSE = "21.10.2026", "22.10.2026", "23.10.2026"
CODES = ["BYF", "BTK", "BYJ", "BZR", "BZV"]


@pytest.fixture()
def wb_path(tmp_path):
    p = tmp_path / "ekim.xlsx"
    shutil.copy2(FIXTURE, p)
    clear_excel_cache()
    return p


def _fresh(p, sheet):
    clear_excel_cache()
    return read_rows(p, sheet), read_blocks(p, sheet)


# ─── Okuma ───────────────────────────────────────────────────────────────

def test_empty_seats_are_not_absorbed_into_blocks(wb_path):
    for sheet in (FULL, PARTIAL, SPARSE):
        rows, blocks = _fresh(wb_path, sheet)
        rmap = {r.row: r for r in rows}
        for b in blocks:
            assert len({rmap[x].balloon for x in b.rows}) == 1, (sheet, b.lead_row)   # blok balon bandını aşmaz
            assert b.pax is None or len(b.rows) <= max(b.pax, len([x for x in b.rows if rmap[x].name]))


def test_free_seat_summary_matches_template(wb_path):
    rows, blocks = _fresh(wb_path, PARTIAL)
    s = free_seat_summary(rows, blocks)
    assert s["BYF"] == {"free": 28, "longest": 28}
    assert sum(v["free"] for v in s.values()) == 42
    rows, blocks = _fresh(wb_path, FULL)
    assert free_seat_summary(rows, blocks) == {}


def test_manifest_contains_only_people(wb_path):
    for sheet in (PARTIAL, SPARSE):
        rows, _ = _fresh(wb_path, sheet)
        for balloon in {r.balloon for r in rows if r.balloon}:
            assert all(m.name for m in build_rows(wb_path, sheet, balloon)), (sheet, balloon)
    assert build_rows(wb_path, PARTIAL, "BYF") == []
    assert sum(len(build_rows(wb_path, FULL, b)) for b in ("BYF", "BYJ", "BZR", "BZV")) == 112


def test_readiness_does_not_count_empty_seats(wb_path):
    assert check_workbook(wb_path, PARTIAL, balloon_capacity=28)["issue_count"] < 5
    assert check_workbook(wb_path, SPARSE, balloon_capacity=28)["issue_count"] < 5


# ─── Balon seçimi ────────────────────────────────────────────────────────

def test_choose_balloon_uses_contiguous_free_seats(wb_path):
    rows, blocks = _fresh(wb_path, PARTIAL)
    assert choose_balloon(rows, blocks, 5, CODES, 28) == {"balloon": "BYF", "overflow": False, "mode": "seat",
        "hotel_match": False}
    assert choose_balloon(rows, blocks, 5, CODES, 28, requested="BZR")["balloon"] == "BZR"     # 6 boş
    assert choose_balloon(rows, blocks, 7, CODES, 28, requested="BZR")["balloon"] == "BYF"     # BZR'ye sığmaz
    # BYF bandını doldur → 7 kişilik grup hiçbir yere sığmaz
    full_byf = [r for r in rows if r.balloon == "BYF"]
    for r in full_byf:
        r.name = "X"
    _, blocks2 = rows, read_blocks(wb_path, PARTIAL)
    rows_after = [r for r in rows]
    res = choose_balloon(rows_after, [b for b in blocks2], 7, CODES, 28)
    assert res["overflow"] is True and res["mode"] == "seat"


# ─── Yazma ───────────────────────────────────────────────────────────────

def test_create_reservation_writes_into_balloon_seats(wb_path):
    before_max = openpyxl.load_workbook(wb_path)[PARTIAL].max_row
    rows, blocks = _fresh(wb_path, PARTIAL)
    bzr_run = free_seat_runs(rows, blocks)["BZR"][0]

    res = create_reservation(wb_path, PARTIAL, pax=3, balloon="BZR", pilot="PILOT 3",
                             fields={"hotel": "OTEL 99", "agency": "ACENTE 99"})
    assert res["mode"] == "seat" and res["rows"] == bzr_run[:3]

    ws = openpyxl.load_workbook(wb_path)[PARTIAL]
    assert ws.max_row == before_max                                 # şablonun altına eklenmedi
    lead = res["lead_row"]
    assert ws.cell(lead, config.COL_PAX).value == 3
    assert ws.cell(lead, config.COL_HOTEL).value == "OTEL 99"
    assert all(ws.cell(r, config.COL_BALLOON).value == "BZR" for r in res["rows"])

    rows, blocks = _fresh(wb_path, PARTIAL)
    new = next(b for b in blocks if b.lead_row == lead)
    assert new.rows == res["rows"] and new.pax == 3                 # kimliksiz yerler bloğa ait
    assert free_seat_summary(rows, blocks)["BZR"]["free"] == 3      # 6 → 3

    write_identity(wb_path, PARTIAL, {res["rows"][0]: {"nationality": "ITA", "sex": "F", "name": "YENI YOLCU",
                                                       "passport_no": "N0000001"}})
    clear_excel_cache()
    names = [m.name for m in build_rows(wb_path, PARTIAL, "BZR")]
    assert "YENI YOLCU" in names and all(names)                     # boş yer manifestoya girmez


def test_delete_reservation_keeps_seat_template(wb_path):
    res = create_reservation(wb_path, PARTIAL, pax=4, balloon="BYF", fields={"hotel": "OTEL 1"})
    delete_reservation(wb_path, PARTIAL, res["rows"])
    ws = openpyxl.load_workbook(wb_path)[PARTIAL]
    for r in res["rows"]:
        assert ws.cell(r, config.COL_BALLOON).value == "BYF"        # balon korunur
        assert ws.cell(r, config.COL_COMPANY).value == "THK"
        assert ws.cell(r, config.COL_PAX).value is None and ws.cell(r, config.COL_HOTEL).value is None
    rows, blocks = _fresh(wb_path, PARTIAL)
    assert free_seat_summary(rows, blocks)["BYF"] == {"free": 28, "longest": 28}


def test_delete_passenger_returns_seat(wb_path):
    res = create_reservation(wb_path, PARTIAL, pax=2, balloon="BYF")
    write_identity(wb_path, PARTIAL, {
        res["rows"][0]: {"nationality": "ESP", "sex": "M", "name": "A B", "passport_no": "P1"},
        res["rows"][1]: {"nationality": "ESP", "sex": "F", "name": "C D", "passport_no": "P2"},
    })
    delete_passenger_from_reservation(wb_path, PARTIAL, lead_row=res["rows"][0], rows=res["rows"],
                                      target_row=res["rows"][1])
    rows, blocks = _fresh(wb_path, PARTIAL)
    block = next(b for b in blocks if b.lead_row == res["rows"][0])
    assert block.pax == 1 and block.rows == [res["rows"][0]]
    assert res["rows"][1] in free_seat_runs(rows, blocks)["BYF"][0]


def test_resize_grows_into_same_balloon_seats_only(wb_path):
    rows, blocks = _fresh(wb_path, PARTIAL)
    run = free_seat_runs(rows, blocks)["BYF"][0]
    res = create_reservation(wb_path, PARTIAL, pax=2, balloon="BYF")
    new_rows = resize_reservation(wb_path, PARTIAL, lead_row=res["lead_row"], rows=res["rows"], new_pax=5)
    assert new_rows == run[:5]

    # BZR bandının son serbest koltuğunda 1 kişilik rezervasyon; büyütme BYF bandına taşamaz
    rows, blocks = _fresh(wb_path, PARTIAL)
    bzr_last = free_seat_runs(rows, blocks)["BZR"][0][-1]
    bzr_res = create_reservation(wb_path, PARTIAL, pax=6, balloon="BZR")
    assert bzr_res["rows"][-1] == bzr_last
    with pytest.raises(ValueError):
        resize_reservation(wb_path, PARTIAL, lead_row=bzr_res["lead_row"], rows=bzr_res["rows"], new_pax=7)


def test_append_template_still_appends(tmp_path):
    """Uygulamanın kendi boş şablonu: koltuk yok → eski davranış (sona ekle)."""
    p = tmp_path / "plan.xlsx"
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "01.11.2026"
    wb.save(p); clear_excel_cache()
    res = create_reservation(p, "01.11.2026", pax=2, balloon="BYF")
    assert res["mode"] == "append" and res["rows"] == [4, 5]
    res2 = create_reservation(p, "01.11.2026", pax=1, balloon="BYJ")
    assert res2["mode"] == "append" and res2["rows"] == [6]
    # silinen blok koltuk olarak kalır ve aynı balonun sonraki küçük grubu onu kullanır
    delete_reservation(p, "01.11.2026", res["rows"])
    res3 = create_reservation(p, "01.11.2026", pax=1, balloon="BYF")
    assert res3["mode"] == "seat" and res3["rows"] == [4]


# ─── API ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch, wb_path):
    monkeypatch.setenv("MANIFESTO_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.setenv("IRTIFA_DB_PATH", str(tmp_path / "seat.db"))
    import app.settings as settings_mod
    importlib.reload(settings_mod)
    import app.main as main_mod
    importlib.reload(main_mod)
    c = TestClient(main_mod.app)
    c.post("/api/auth/setup", json={"username": "admin", "display_name": "Y", "password": "strong-pass"})
    s = settings_mod.load()
    s.planning_xlsx = str(wb_path); s.balloon_codes = list(CODES); s.is_setup_complete = True
    settings_mod.save(s)
    return c


def test_api_create_with_identities_fills_free_seats(client, wb_path):
    load = client.get("/api/planning/load", params={"sheet": PARTIAL}).json()
    assert load["free_seats"]["BYF"]["free"] == 28
    r = client.post("/api/planning/create-with-identities", json={
        "sheet": PARTIAL, "pax": 2, "hotel": "OTEL 5", "agency": "ACENTE 5",
        "identities": [{"nationality": "KOR", "sex": "M", "name": "YOLCU A", "passport_no": "M12345678"},
                       {"nationality": "KOR", "sex": "F", "name": "YOLCU B", "passport_no": "M87654321"}],
        "expected_revision": load["workbook_revision"],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    ws = openpyxl.load_workbook(wb_path)[PARTIAL]
    assert ws.max_row == 117                                         # şablon büyümedi
    assert all(ws.cell(row, config.COL_BALLOON).value == body.get("balloon", "BYF") for row in body["rows"])
    clear_excel_cache()
    assert {m.name for m in build_rows(wb_path, PARTIAL, "BYF")} == {"YOLCU A", "YOLCU B"}


def test_append_template_gap_does_not_force_overflow(tmp_path):
    """Ekleme şablonunda silmeden kalan 1 koltukluk boşluk, 3 kişilik grubu overflow'a düşürmez."""
    p = tmp_path / "plan.xlsx"
    wb = openpyxl.Workbook(); wb.active.title = "02.11.2026"; wb.save(p); clear_excel_cache()
    a = create_reservation(p, "02.11.2026", pax=1, balloon="BYF")
    create_reservation(p, "02.11.2026", pax=2, balloon="BYF")
    delete_reservation(p, "02.11.2026", a["rows"])           # satır 4 BYF koltuğu olarak kaldı
    rows, blocks = _fresh(p, "02.11.2026")
    res = choose_balloon(rows, blocks, 3, CODES, 28)
    assert res == {"balloon": "BYF", "overflow": False, "mode": "append", "hotel_match": False}
