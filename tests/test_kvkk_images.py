"""KVKK (brief §10): yazım sonrası görsel silme ve günlük temizlikte yerel gün."""
from __future__ import annotations

import datetime as dt

import pytest
from starlette.requests import Request

from app import passport_store
from app import settings as settings_mod
from app.db import connect, init_db


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("IRTIFA_DB_PATH", str(tmp_path / "kvkk.db"))
    monkeypatch.setattr(passport_store, "ROOT", tmp_path / "incoming")
    init_db()
    import app.main as main_mod
    return main_mod


def _insert_extraction(path: str | None, created_at: str | None = None) -> int:
    conn = connect()
    try:
        if created_at:
            cur = conn.execute(
                "INSERT INTO passport_extraction(name, document_number, source_media_id, created_at) "
                "VALUES ('AD', 'X1', ?, ?)",
                (path, created_at),
            )
        else:
            cur = conn.execute(
                "INSERT INTO passport_extraction(name, document_number, source_media_id) VALUES ('AD', 'X1', ?)",
                (path,),
            )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _row(extraction_id: int):
    conn = connect()
    try:
        return conn.execute(
            "SELECT status, source_media_id FROM passport_extraction WHERE id = ?", (extraction_id,)
        ).fetchone()
    finally:
        conn.close()


def test_write_deletes_staged_image_when_setting_enabled(env, monkeypatch):
    main_mod = env
    monkeypatch.setattr(main_mod, "_load_settings", lambda: settings_mod.Settings(delete_images_after_write=True))
    image = passport_store.save_image(b"jpeg-bytes", "passport.jpg")
    extraction_id = _insert_extraction(str(image))

    removed = main_mod._mark_extractions_approved([{"extraction_id": extraction_id}], "22.06.2026", [4])

    assert removed == 1
    assert not image.exists()
    row = _row(extraction_id)
    assert row["status"] == "approved"
    assert row["source_media_id"] is None


def test_write_keeps_image_when_setting_disabled(env, monkeypatch):
    main_mod = env
    monkeypatch.setattr(main_mod, "_load_settings", lambda: settings_mod.Settings(delete_images_after_write=False))
    image = passport_store.save_image(b"jpeg-bytes", "passport.jpg")
    extraction_id = _insert_extraction(str(image))

    removed = main_mod._mark_extractions_approved([{"extraction_id": extraction_id}], "22.06.2026", [4])

    assert removed == 0
    assert image.exists()
    assert _row(extraction_id)["source_media_id"] == str(image)


def test_delete_image_refuses_paths_outside_root(tmp_path):
    outside = tmp_path / "elsewhere.jpg"
    outside.write_bytes(b"x")
    assert passport_store.delete_image(str(outside)) is False
    assert outside.exists()
    assert passport_store.delete_image(None) is False
    assert passport_store.delete_image(str(passport_store.ROOT / "yok.jpg")) is False


def test_cleanup_matches_local_calendar_day_not_utc(env):
    """created_at UTC'dir; TR'de 00:00-03:00 arası yüklenen kayıtlar o günün temizliğinde silinmeli."""
    main_mod = env
    # UTC 23:30 → yerel gün (TR'de) bir sonraki gün. Beklenti makinenin saat diliminden türetilir.
    utc_moment = dt.datetime(2026, 6, 21, 23, 30, 0, tzinfo=dt.timezone.utc)
    local_day = utc_moment.astimezone().date()
    utc_day = utc_moment.date()
    extraction_id = _insert_extraction(None, created_at=utc_moment.strftime("%Y-%m-%d %H:%M:%S"))

    request = Request({"type": "http", "headers": []})
    if local_day != utc_day:
        # UTC gününe göre temizlik kaydı silmemeli
        main_mod.api_passport_cleanup(request, {"day": utc_day.isoformat()})
        assert _row(extraction_id) is not None

    main_mod.api_passport_cleanup(request, {"day": local_day.isoformat()})
    assert _row(extraction_id) is None
