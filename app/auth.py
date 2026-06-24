"""Offline local accounts and cookie-backed sessions."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.db import connect, init_db


SESSION_COOKIE = "irtifa_session"
SESSION_DAYS = 14
_hasher = PasswordHasher()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def setup_required() -> bool:
    conn = connect()
    try:
        try:
            return conn.execute("SELECT COUNT(*) FROM app_user").fetchone()[0] == 0
        except Exception:
            conn.close()
            init_db()
            conn = connect()
            return conn.execute("SELECT COUNT(*) FROM app_user").fetchone()[0] == 0
    finally:
        conn.close()


def create_initial_admin(username: str, display_name: str, password: str) -> tuple[dict, str]:
    if not setup_required():
        raise ValueError("İlk yönetici hesabı zaten oluşturulmuş.")
    _validate_password(password)
    recovery_code = "-".join(
        secrets.token_hex(2).upper() for _ in range(4)
    )
    conn = connect()
    try:
        cursor = conn.execute(
            """
            INSERT INTO app_user(username, display_name, password_hash, role)
            VALUES (?, ?, ?, 'admin')
            """,
            (username.strip(), display_name.strip() or username.strip(), _hasher.hash(password)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO recovery_code(id, code_hash, used_at) VALUES (1, ?, NULL)",
            (_hasher.hash(recovery_code),),
        )
        conn.commit()
        return get_user(cursor.lastrowid), recovery_code
    finally:
        conn.close()


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Parola en az 8 karakter olmalı.")


def get_user(user_id: int) -> dict:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT id, username, display_name, role, is_active, created_at, last_login_at "
            "FROM app_user WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            raise KeyError(user_id)
        return dict(row)
    finally:
        conn.close()


def authenticate(username: str, password: str) -> dict | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM app_user WHERE username = ? COLLATE NOCASE AND is_active = 1",
            (username.strip(),),
        ).fetchone()
        if not row:
            return None
        try:
            _hasher.verify(row["password_hash"], password)
        except VerifyMismatchError:
            return None
        if _hasher.check_needs_rehash(row["password_hash"]):
            conn.execute(
                "UPDATE app_user SET password_hash = ? WHERE id = ?",
                (_hasher.hash(password), row["id"]),
            )
        conn.execute(
            "UPDATE app_user SET last_login_at = datetime('now') WHERE id = ?",
            (row["id"],),
        )
        conn.commit()
        return get_user(row["id"])
    finally:
        conn.close()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO auth_session(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (_hash_token(token), user_id, expires.strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
    finally:
        conn.close()
    return token


def user_for_session(token: str | None) -> dict | None:
    if not token:
        return None
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.display_name, u.role, u.is_active,
                   u.created_at, u.last_login_at
            FROM auth_session s
            JOIN app_user u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires_at > datetime('now') AND u.is_active = 1
            """,
            (_hash_token(token),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_session(token: str | None) -> None:
    if not token:
        return
    conn = connect()
    try:
        conn.execute("DELETE FROM auth_session WHERE token_hash = ?", (_hash_token(token),))
        conn.commit()
    finally:
        conn.close()


def list_users() -> list[dict]:
    conn = connect()
    try:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT id, username, display_name, role, is_active, created_at, last_login_at "
                "FROM app_user ORDER BY display_name"
            ).fetchall()
        ]
    finally:
        conn.close()


def create_user(username: str, display_name: str, password: str, role: str) -> dict:
    _validate_password(password)
    if role not in {"admin", "operator"}:
        raise ValueError("Geçersiz kullanıcı rolü.")
    conn = connect()
    try:
        cursor = conn.execute(
            """
            INSERT INTO app_user(username, display_name, password_hash, role)
            VALUES (?, ?, ?, ?)
            """,
            (username.strip(), display_name.strip() or username.strip(), _hasher.hash(password), role),
        )
        conn.commit()
        return get_user(cursor.lastrowid)
    finally:
        conn.close()


def reset_admin_with_recovery(code: str, new_password: str) -> None:
    _validate_password(new_password)
    conn = connect()
    try:
        row = conn.execute(
            "SELECT code_hash, used_at FROM recovery_code WHERE id = 1"
        ).fetchone()
        if not row or row["used_at"]:
            raise ValueError("Kurtarma kodu geçersiz veya daha önce kullanılmış.")
        try:
            _hasher.verify(row["code_hash"], code.strip().upper())
        except VerifyMismatchError as exc:
            raise ValueError("Kurtarma kodu geçersiz.") from exc
        admin = conn.execute(
            "SELECT id FROM app_user WHERE role = 'admin' ORDER BY id LIMIT 1"
        ).fetchone()
        if not admin:
            raise ValueError("Yönetici hesabı bulunamadı.")
        conn.execute(
            "UPDATE app_user SET password_hash = ?, is_active = 1 WHERE id = ?",
            (_hasher.hash(new_password), admin["id"]),
        )
        conn.execute("UPDATE recovery_code SET used_at = datetime('now') WHERE id = 1")
        conn.execute("DELETE FROM auth_session")
        conn.commit()
    finally:
        conn.close()
