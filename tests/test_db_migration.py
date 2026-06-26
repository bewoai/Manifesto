from __future__ import annotations

import sqlite3

from app.db import init_db


def test_partial_passport_migration_resumes(tmp_path):
    db_path = tmp_path / "partial.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE passport_extraction (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            source_media_id TEXT,
            mrz_format TEXT,
            nationality TEXT,
            sex TEXT,
            name TEXT,
            document_number TEXT,
            birth_date TEXT,
            expiry_date TEXT,
            checks_ok INTEGER NOT NULL DEFAULT 0,
            flags TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            planning_date TEXT,
            planning_row INTEGER,
            agency TEXT,
            confidence_score REAL
        );
        """
    )
    conn.commit()
    conn.close()

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(passport_extraction)")
    }
    conn.close()
    assert {
        "confidence_score",
        "processing_route",
        "ai_model_used",
        "fallback_reason",
        "requires_manual_review",
        "manual_review_reason",
    } <= columns


def test_db_backup_created_on_init(tmp_path):
    db_path = tmp_path / "existing.db"
    # Create valid initial SQLite DB with a dummy table
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE dummy (val TEXT)")
    conn.execute("INSERT INTO dummy VALUES ('hello')")
    conn.commit()
    conn.close()

    init_db(db_path)

    backup_path = db_path.with_suffix(".db.bak")
    assert backup_path.exists()
    
    # Check that backup is a valid DB containing our dummy table
    conn_bak = sqlite3.connect(backup_path)
    rows = conn_bak.execute("SELECT val FROM dummy").fetchall()
    conn_bak.close()
    assert len(rows) == 1
    assert rows[0][0] == 'hello'


def test_db_contains_new_relational_tables(tmp_path):
    db_path = tmp_path / "new_schema.db"
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    tables = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    conn.close()

    expected_tables = {
        "passengers",
        "flights",
        "reservations",
        "reservation_passengers",
        "agencies",
        "hotels",
        "drivers",
        "manifests",
        "settings",
        "import_logs",
        "app_logs",
    }
    assert expected_tables <= tables

