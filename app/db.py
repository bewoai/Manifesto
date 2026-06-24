"""SQLite şeması (hibrit mimari).

DB planlama sayfasını TUTMAZ — o Excel'de kalır. DB yalnızca pasaport
çıkarımlarını, flag'leri ve audit kaydını tutar (brief §10, §12.1).
SQLite -> ileride Postgres'e taşınabilir.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

APP_DATA_DIR = Path(os.getenv("APPDATA") or Path.home() / ".config") / "Irtifa"
DB_PATH = APP_DATA_DIR / "irtifa.db"


def default_db_path() -> Path:
    explicit = os.getenv("IRTIFA_DB_PATH")
    if explicit:
        return Path(explicit)
    settings_path = os.getenv("MANIFESTO_SETTINGS")
    if settings_path:
        return Path(settings_path).with_name("irtifa.db")
    return DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS passport_extraction (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    source_media_id TEXT,                 -- WhatsApp media_id (Faz 2)
    mrz_format      TEXT,                 -- TD3 / TD1
    nationality     TEXT,                 -- alpha-3
    sex             TEXT,                 -- M / F / X
    name            TEXT,

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
    agency          TEXT,
    -- v2: multi-layer OCR & confidence
    confidence_score REAL,
    processing_route TEXT,
    ai_model_used    TEXT,
    fallback_reason  TEXT,
    requires_manual_review INTEGER NOT NULL DEFAULT 0,
    manual_review_reason   TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL DEFAULT (datetime('now')),
    actor        TEXT,
    action       TEXT NOT NULL,          -- approved / rejected / edited / exported
    extraction_id INTEGER,
    sheet        TEXT,
    reservation_row INTEGER,
    detail       TEXT,
    FOREIGN KEY (extraction_id) REFERENCES passport_extraction(id)
);

CREATE INDEX IF NOT EXISTS idx_extraction_status ON passport_extraction(status);
CREATE INDEX IF NOT EXISTS idx_extraction_docno ON passport_extraction(document_number);
CREATE INDEX IF NOT EXISTS idx_extraction_manual ON passport_extraction(requires_manual_review);

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

CREATE TABLE IF NOT EXISTS app_user (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name  TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK(role IN ('admin', 'operator')),
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS auth_session (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES app_user(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS recovery_code (
    id         INTEGER PRIMARY KEY CHECK(id = 1),
    code_hash  TEXT NOT NULL,
    used_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor);
CREATE INDEX IF NOT EXISTS idx_session_expiry ON auth_session(expires_at);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    db_path = Path(db_path) if db_path else default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | None = None) -> None:
    db_path = Path(db_path) if db_path else default_db_path()
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        
        # audit_log migration
        columns_audit = {row["name"] for row in conn.execute("PRAGMA table_info(audit_log)")}
        if "sheet" not in columns_audit:
            conn.execute("ALTER TABLE audit_log ADD COLUMN sheet TEXT")
        if "reservation_row" not in columns_audit:
            conn.execute("ALTER TABLE audit_log ADD COLUMN reservation_row INTEGER")
            
        # passport_extraction v2 migration
        columns_pe = {row["name"] for row in conn.execute("PRAGMA table_info(passport_extraction)")}
        if "confidence_score" not in columns_pe:
            conn.execute("ALTER TABLE passport_extraction ADD COLUMN confidence_score REAL")
            conn.execute("ALTER TABLE passport_extraction ADD COLUMN processing_route TEXT")
            conn.execute("ALTER TABLE passport_extraction ADD COLUMN ai_model_used TEXT")
            conn.execute("ALTER TABLE passport_extraction ADD COLUMN fallback_reason TEXT")
            conn.execute("ALTER TABLE passport_extraction ADD COLUMN requires_manual_review INTEGER NOT NULL DEFAULT 0")
            conn.execute("ALTER TABLE passport_extraction ADD COLUMN manual_review_reason TEXT")
            
        conn.execute("DELETE FROM audit_log WHERE ts < datetime('now', '-365 days')")
        conn.execute("DELETE FROM auth_session WHERE expires_at < datetime('now')")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"DB hazır -> {DB_PATH}")
