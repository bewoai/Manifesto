"""SQLite şeması (hibrit mimari).

DB planlama sayfasını TUTMAZ — o Excel'de kalır. DB yalnızca pasaport
çıkarımlarını, flag'leri ve audit kaydını tutar (brief §10, §12.1).
SQLite -> ileride Postgres'e taşınabilir.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import DATA_DIR

DB_PATH = DATA_DIR / "manifesto.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS passport_extraction (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    source_media_id TEXT,                 -- WhatsApp media_id (Faz 2)
    mrz_format      TEXT,                 -- TD3 / TD1
    nationality     TEXT,                 -- alpha-3
    sex             TEXT,                 -- M / F / X
    name            TEXT,
    document_number TEXT,
    birth_date      TEXT,
    expiry_date     TEXT,
    checks_ok       INTEGER NOT NULL DEFAULT 0,
    flags           TEXT,                 -- virgülle ayrık Flag listesi
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending/approved/rejected
    -- eşleştirme (Faz 2): hangi planlama satırına yazıldı
    planning_date   TEXT,
    planning_row    INTEGER,
    agency          TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL DEFAULT (datetime('now')),
    actor        TEXT,                    -- operatör
    action       TEXT NOT NULL,          -- approved / rejected / edited / exported
    extraction_id INTEGER,
    detail       TEXT,
    FOREIGN KEY (extraction_id) REFERENCES passport_extraction(id)
);

CREATE INDEX IF NOT EXISTS idx_extraction_status ON passport_extraction(status);
CREATE INDEX IF NOT EXISTS idx_extraction_docno ON passport_extraction(document_number);

CREATE TABLE IF NOT EXISTS weather_measurement (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    measured_at        TEXT NOT NULL,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    provider           TEXT NOT NULL,
    location_name      TEXT,
    latitude           REAL,
    longitude          REAL,
    temperature_c      REAL,
    wind_speed_kmh     REAL,
    wind_gust_kmh      REAL,
    wind_direction_deg REAL,
    visibility_m       REAL,
    precipitation_mm   REAL,
    cloud_cover_pct    REAL,
    weather_code       INTEGER,
    risk_level         TEXT NOT NULL,
    flight_status      TEXT NOT NULL,
    summary            TEXT,
    payload_json       TEXT
);

CREATE INDEX IF NOT EXISTS idx_weather_measured_at ON weather_measurement(measured_at);
CREATE INDEX IF NOT EXISTS idx_weather_risk ON weather_measurement(risk_level);
"""


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"DB hazır -> {DB_PATH}")
