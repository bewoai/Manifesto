"""Windows DPAPI-backed local secret storage."""
from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path


def _store_path() -> Path:
    explicit = os.getenv("IRTIFA_SECRET_STORE")
    if explicit:
        return Path(explicit)
    settings_path = os.getenv("MANIFESTO_SETTINGS")
    if settings_path:
        return Path(settings_path).with_name("secrets.dat")
    return Path(os.getenv("APPDATA") or Path.home() / ".config") / "Irtifa" / "secrets.dat"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Korumalı anahtar deposu yalnızca Windows'ta kullanılabilir.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, _buffer = _blob(data)
    out_blob = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(in_blob), "Irtifa", None, None, None, 0, ctypes.byref(out_blob)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Korumalı anahtar deposu yalnızca Windows'ta kullanılabilir.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, _buffer = _blob(data)
    out_blob = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _read_all() -> dict[str, str]:
    store_path = _store_path()
    if not store_path.exists():
        return {}
    try:
        encrypted = base64.b64decode(store_path.read_bytes())
        return json.loads(_unprotect(encrypted).decode("utf-8"))
    except Exception:
        return {}


def _write_all(values: dict[str, str]) -> None:
    store_path = _store_path()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(values, ensure_ascii=False).encode("utf-8")
    store_path.write_bytes(base64.b64encode(_protect(payload)))


def get_secret(key: str) -> str:
    return _read_all().get(key, "")


def set_secret(key: str, value: str) -> None:
    values = _read_all()
    if value:
        values[key] = value
    else:
        values.pop(key, None)
    _write_all(values)


def migrate_file_secret(key: str, value: str) -> str:
    """Store a service-account file's content and return the DPAPI marker."""
    if not value:
        return ""
    candidate = Path(value)
    secret = candidate.read_text(encoding="utf-8") if candidate.exists() else value
    set_secret(key, secret)
    return f"dpapi:{key}"
