"""Liste işaret kuralları, acenteye kayıt, çıkarım meta kolonlarının kalıcılığı."""
from __future__ import annotations

import importlib
import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from app import settings as settings_mod
from app.list_marks import MARK_RULES, annotation_matches, normalize_agency_key, normalize_rules


@pytest.mark.parametrize("rule,annotation,expected", [
    ("all", "", True),
    ("all", "strike", True),
    ("any_mark", "", False),
    ("any_mark", "✓", True),
    ("any_mark", "strike", False),
    ("check", "✓", True),
    ("check", "tick", True),
    ("check", "SI", False),
    ("highlight", "highlight", True),
    ("highlight", "fosfor", True),
    ("highlight", "21", False),
    ("number", "21", True),
    ("number", "7", True),
    ("number", "B", False),
    ("number", "1234", False),
    ("yes", "SI", True),
    ("yes", "SÍ", True),
    ("yes", "Evet", True),
    ("yes", "no", False),
    ("letter_b", "B", True),
    ("letter_b", "b", True),
    ("letter_b", "✓", False),
    ("nope", "✓", False),
])
def test_annotation_matches(rule, annotation, expected):
    assert annotation_matches(rule, annotation) is expected


def test_normalize_rules_and_agency_key():
    assert normalize_agency_key("  Karavan Turizm ") == "karavan turizm"
    assert normalize_agency_key("İTAKA") == normalize_agency_key("itaka")
    assert normalize_rules({"Karavan": "highlight", "X": "bogus", "": "check"}) == {"karavan": "highlight"}
    assert normalize_rules("not a dict") == {}
    assert set(MARK_RULES) >= {"all", "any_mark", "check", "highlight", "number", "yes", "letter_b"}


def test_settings_keep_mark_rules_normalized(tmp_path):
    s = settings_mod.Settings(list_mark_rules={"Aytorex": "letter_b", "bad": "zzz"}).normalized()
    assert s.list_mark_rules == {"aytorex": "letter_b"}
    path = tmp_path / "settings.json"
    settings_mod.save(s, path)
    assert settings_mod.load(path).list_mark_rules == {"aytorex": "letter_b"}


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("MANIFESTO_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.setenv("IRTIFA_DB_PATH", str(tmp_path / "marks.db"))
    importlib.reload(settings_mod)
    import app.main as main_mod
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


def test_mark_rule_endpoints_roundtrip(client):
    r = client.get("/api/lists/mark-rules")
    assert r.status_code == 200 and r.json()["rules"] == {}
    assert any(a["id"] == "highlight" for a in r.json()["available"])

    r = client.post("/api/lists/mark-rule", json={"agency": "Karavan Turizm", "rule": "highlight"})
    assert r.status_code == 200 and r.json()["rules"] == {"karavan turizm": "highlight"}
    assert client.get("/api/lists").json()["mark_rules"] == {"karavan turizm": "highlight"}

    assert client.post("/api/lists/mark-rule", json={"agency": "X", "rule": "bogus"}).status_code == 422
    assert client.post("/api/lists/mark-rule", json={"agency": "", "rule": "check"}).status_code == 422

    r = client.post("/api/lists/mark-rule", json={"agency": "KARAVAN TURİZM", "rule": ""})
    assert r.json()["rules"] == {}


def test_init_db_adds_meta_columns_to_existing_database(tmp_path, monkeypatch):
    """Eski şemayla oluşmuş DB açılınca yeni kolonlar eklenir (yarım yükseltme güvenli)."""
    import sqlite3
    from app.db import connect, init_db

    db_path = tmp_path / "old.db"
    monkeypatch.setenv("IRTIFA_DB_PATH", str(db_path))
    raw = sqlite3.connect(db_path)
    raw.execute("""CREATE TABLE passport_extraction (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
        source_media_id TEXT, mrz_format TEXT, nationality TEXT, sex TEXT, name TEXT, document_number TEXT,
        birth_date TEXT, expiry_date TEXT, checks_ok INTEGER NOT NULL DEFAULT 0, flags TEXT,
        status TEXT NOT NULL DEFAULT 'pending', planning_date TEXT, planning_row INTEGER, agency TEXT)""")
    raw.commit(); raw.close()

    init_db()
    cols = {r["name"] for r in connect().execute("PRAGMA table_info(passport_extraction)")}
    assert {"source_kind", "annotation", "selected", "group_json", "document_type"} <= cols


def test_insert_extraction_persists_meta(tmp_path, monkeypatch):
    import datetime as dt
    from app.db import connect, init_db
    import app.main as main_mod
    from app.vision.extractor import process_image
    from app.vision.providers import OcrResult

    monkeypatch.setenv("IRTIFA_DB_PATH", str(tmp_path / "meta.db"))
    init_db()

    class P:
        name = "fake"

        def read(self, b, m):
            return OcrResult(status="success", source="x", kind="printed_list",
                             group={"agency": "Karavan", "pax": 2, "hotel": "", "date": "", "booking_code": "",
                                    "nationality_hint": "GBR", "note": ""},
                             passengers=[{"format": "NONE", "lines": [],
                                          "fields": {"first_name": "SUSAN", "last_name": "HOLDER", "nationality": "",
                                                     "gender": "F", "document_no": "140134006", "document_type": "P",
                                                     "birth_date": "1949-03-16", "expiry_date": ""},
                                          "confidence": 0.95, "annotation": "highlight", "selected": None}])

    rec = process_image(b"img", ocr_provider=P(), today=dt.date(2010, 1, 1))[0]
    fields = rec.to_fields()
    conn = connect()
    new_id = main_mod._insert_extraction(conn, tmp_path / "img.jpg", rec, fields)
    conn.commit()
    row = conn.execute("SELECT * FROM passport_extraction WHERE id = ?", (new_id,)).fetchone()
    conn.close()
    assert row["source_kind"] == "printed_list"
    assert row["annotation"] == "highlight"
    assert row["selected"] is None
    assert row["document_type"] == "P"
    assert json.loads(row["group_json"])["agency"] == "Karavan"
    assert row["nationality"] == "GBR"       # grup ipucu uygulandı
