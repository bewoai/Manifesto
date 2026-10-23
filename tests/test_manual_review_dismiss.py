"""Manuel kontrol kuyruğunu toplu temizleme: seçili / tümü, paylaşılan görsel korunur."""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("MANIFESTO_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.setenv("IRTIFA_DB_PATH", str(tmp_path / "review.db"))
    import app.settings as settings_mod
    importlib.reload(settings_mod)
    import app.main as main_mod
    importlib.reload(main_mod)
    images = tmp_path / "images"
    images.mkdir()
    monkeypatch.setattr(main_mod, "PASSPORT_IMAGE_ROOT", images)
    import app.passport_store as store
    monkeypatch.setattr(store, "ROOT", images)
    client = TestClient(main_mod.app)
    client.__enter__()   # startup: init_db
    from app.db import connect

    def add(source=None, pending=True, name="X"):
        conn = connect()
        try:
            cur = conn.execute(
                "INSERT INTO passport_extraction (source_media_id, name, status, requires_manual_review) "
                "VALUES (?, ?, 'pending', ?)",
                (str(source) if source else None, name, 1 if pending else 0),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    yield client, add, images
    client.__exit__(None, None, None)


def _pending_ids(client):
    return [i["id"] for i in client.get("/api/passport/manual-review").json()["items"]]


def test_dismiss_selected_keeps_others_and_shared_image(env):
    client, add, images = env
    shared = images / "liste.jpg"; shared.write_bytes(b"x")
    alone = images / "pasaport.jpg"; alone.write_bytes(b"x")
    a = add(shared, name="A"); b = add(shared, name="B"); c = add(alone, name="C")
    r = client.post("/api/passport/manual-review/dismiss", json={"ids": [a, c]})
    assert r.status_code == 200, r.text
    assert r.json()["dismissed"] == 2
    assert _pending_ids(client) == [b]
    assert shared.exists()          # B hâlâ kullanıyor
    assert not alone.exists()       # son kullanan kaldırıldı → silindi


def test_dismiss_all_clears_queue_and_images(env):
    client, add, images = env
    files = []
    for n in range(5):
        f = images / f"g{n}.jpg"; f.write_bytes(b"x"); files.append(f)
        add(f)
    done = add(None, pending=False)   # kuyrukta olmayan kayda dokunulmaz
    r = client.post("/api/passport/manual-review/dismiss", json={"all": True})
    assert r.json() == {"success": True, "dismissed": 5, "removed_files": 5}
    assert _pending_ids(client) == []
    assert not any(f.exists() for f in files)
    from app.db import connect
    conn = connect()
    try:
        assert conn.execute("SELECT status FROM passport_extraction WHERE id = ?", (done,)).fetchone()[0] == "pending"
    finally:
        conn.close()


@pytest.mark.parametrize("body", [{}, {"ids": []}, {"ids": ["x"]}])
def test_dismiss_requires_selection(env, body):
    client, _, _ = env
    assert client.post("/api/passport/manual-review/dismiss", json=body).status_code == 422
