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
