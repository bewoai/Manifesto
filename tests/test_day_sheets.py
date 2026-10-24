"""Gün seçicileri yalnız tarih adlı sayfaları, tarih sırasıyla görür ("Sayfa1" gibi özetler değil)."""
from __future__ import annotations

import importlib
import json

import openpyxl
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch, tmp_path):
    plan = tmp_path / "plan.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "22.10.2026"
    for name in ["Sayfa1", "3.10.2026", "21.10.2026"]:
        wb.create_sheet(name)
    wb.save(plan)
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"planning_xlsx": str(plan)}), encoding="utf-8")
    monkeypatch.setenv("MANIFESTO_SETTINGS", str(settings_path))
    monkeypatch.setenv("IRTIFA_DB_PATH", str(tmp_path / "s.db"))
    import app.settings as settings_mod
    importlib.reload(settings_mod)
    import app.main as main_mod
    importlib.reload(main_mod)
    with TestClient(main_mod.app) as c:
        yield c


def test_only_day_sheets_in_date_order(client):
    data = client.get("/api/planning/sheets").json()
    assert data["sheets"] == ["3.10.2026", "21.10.2026", "22.10.2026"]
    assert data["other_sheets"] == ["Sayfa1"]
