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
