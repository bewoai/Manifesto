"""Kalıcı listeler (balon/otel/şoför...) add/delete + otomatik öğrenme — PII'siz."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    # İzole geçici settings dosyası
    tmp = os.path.join(tempfile.mkdtemp(), "settings.json")
    monkeypatch.setenv("MANIFESTO_SETTINGS", tmp)
    # settings modülü SETTINGS_PATH'i import anında okur → yeniden yükle
    import importlib
    import app.settings as settings_mod
    importlib.reload(settings_mod)
    import app.main as main_mod
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


def test_add_and_delete_balloon(client):
    r = client.post("/api/lists/add", json={"category": "balloon", "value": "abc"})
    assert r.status_code == 200
    assert "ABC" in r.json()["balloons"]  # upper'lanır

    r = client.post("/api/lists/delete", json={"category": "balloon", "value": "abc"})
    assert "ABC" not in r.json()["balloons"]  # büyük/küçük harf duyarsız sil


def test_add_hotel_dedupes_case_insensitive(client):
    client.post("/api/lists/add", json={"category": "hotel", "value": "Argos"})
    r = client.post("/api/lists/add", json={"category": "hotel", "value": "ARGOS"})
    hotels = r.json()["options"]["hotel"]
    assert sum(1 for h in hotels if h.upper() == "ARGOS") == 1


def test_invalid_category_rejected(client):
    r = client.post("/api/lists/add", json={"category": "nope", "value": "x"})
    assert r.status_code == 422


def test_empty_value_rejected(client):
    r = client.post("/api/lists/add", json={"category": "hotel", "value": "  "})
    assert r.status_code == 422


def test_remember_values_adds_new_only(client):
    import app.main as main_mod
    import app.settings as settings_mod
    s = settings_mod.Settings()
    s.operation_options["hotel"] = ["ARGOS"]
    assert main_mod._remember_values(s, {"hotel": "ARGOS"}) is False  # mevcut → eklenmez
    assert main_mod._remember_values(s, {"hotel": "MUSTAFA", "driver": "AHMET"}) is True
    assert "MUSTAFA" in s.operation_options["hotel"]
    assert "AHMET" in s.operation_options["driver"]


def test_get_lists_shape(client):
    r = client.get("/api/lists")
    j = r.json()
    assert "balloons" in j and "capacity" in j and "options" in j
    assert set(j["options"].keys()) == {"hotel", "driver", "agency", "pilot", "coming_place", "reserved_by"}
