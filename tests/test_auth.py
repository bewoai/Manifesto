from app import auth
from app.db import init_db


def test_local_admin_login_and_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv("IRTIFA_DB_PATH", str(tmp_path / "auth.db"))
    init_db()
    user, recovery = auth.create_initial_admin("admin", "Yönetici", "strong-pass")
    assert user["role"] == "admin"
    assert auth.authenticate("admin", "wrong") is None
    assert auth.authenticate("admin", "strong-pass")["username"] == "admin"

    token = auth.create_session(user["id"])
    assert auth.user_for_session(token)["id"] == user["id"]
    auth.reset_admin_with_recovery(recovery, "new-strong-pass")
    assert auth.user_for_session(token) is None
    assert auth.authenticate("admin", "new-strong-pass")


def test_api_requires_login_and_enforces_admin_role(tmp_path, monkeypatch):
    import importlib
    from fastapi.testclient import TestClient

    monkeypatch.setenv("IRTIFA_DB_PATH", str(tmp_path / "api-auth.db"))
    monkeypatch.setenv("MANIFESTO_SETTINGS", str(tmp_path / "settings.json"))
    import app.main as main_mod
    importlib.reload(main_mod)

    with TestClient(main_mod.app) as admin_client:
        setup = admin_client.post(
            "/api/auth/setup",
            json={
                "username": "admin",
                "display_name": "Yönetici",
                "password": "strong-pass",
            },
        )
        assert setup.status_code == 200
        assert admin_client.get("/api/settings").status_code == 200
        created = admin_client.post(
            "/api/admin/users",
            json={
                "username": "operator",
                "display_name": "Operatör",
                "password": "operator-pass",
                "role": "operator",
            },
        )
        assert created.status_code == 200

    with TestClient(main_mod.app) as anonymous_client:
        assert anonymous_client.get("/api/settings").status_code == 401

    with TestClient(main_mod.app) as operator_client:
        login = operator_client.post(
            "/api/auth/login",
            json={"username": "operator", "password": "operator-pass"},
        )
        assert login.status_code == 200
        assert operator_client.get("/api/lists").status_code == 200
        assert operator_client.get("/api/admin/users").status_code == 403
        assert operator_client.put("/api/settings", json={}).status_code == 403


def test_frontend_license_skip_enters_manual_workspace():
    from pathlib import Path

    app_js = Path("frontend/app.js").read_text(encoding="utf-8")
    assert "if (!appStatus.licensed && !appStatus.skipped)" in app_js
