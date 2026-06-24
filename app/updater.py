"""Signed GitHub release manifest updater."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.version import APP_VERSION


UPDATE_DIR = Path(os.getenv("LOCALAPPDATA") or Path.home()) / "Irtifa" / "updates"


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.lstrip("v").split("."))
    except ValueError:
        return (0,)


def check(manifest_url: str) -> dict:
    if not manifest_url:
        return {"configured": False, "current_version": APP_VERSION, "available": False}
    with urllib.request.urlopen(manifest_url, timeout=8) as response:
        manifest = json.loads(response.read().decode("utf-8"))
    latest = str(manifest.get("version", "0.0.0"))
    return {
        "configured": True,
        "current_version": APP_VERSION,
        "latest_version": latest,
        "available": _version_tuple(latest) > _version_tuple(APP_VERSION),
        "release_notes": manifest.get("release_notes", ""),
        "manifest": manifest,
    }


def stage(manifest: dict, public_key_b64: str) -> Path:
    required = ("version", "url", "sha256", "signature")
    if any(not manifest.get(key) for key in required):
        raise ValueError("Güncelleme manifesti eksik.")
    if not public_key_b64:
        raise ValueError("Güncelleme imza anahtarı ayarlanmamış.")
    UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    target = UPDATE_DIR / "Irtifa.new.exe"
    with urllib.request.urlopen(manifest["url"], timeout=60) as response:
        target.write_bytes(response.read())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest.lower() != str(manifest["sha256"]).lower():
        target.unlink(missing_ok=True)
        raise ValueError("Güncelleme dosyasının SHA-256 doğrulaması başarısız.")
    signed = f"{manifest['version']}\n{manifest['url']}\n{manifest['sha256']}".encode("utf-8")
    public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
    public_key.verify(base64.b64decode(manifest["signature"]), signed)
    (UPDATE_DIR / "pending.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target


def launch_pending_install() -> bool:
    pending = UPDATE_DIR / "pending.json"
    staged = UPDATE_DIR / "Irtifa.new.exe"
    if not pending.exists() or not staged.exists() or not getattr(sys, "frozen", False):
        return False
    current = Path(sys.executable).resolve()
    backup = current.with_suffix(".previous.exe")
    script = UPDATE_DIR / "install_update.cmd"
    script.write_text(
        "\r\n".join([
            "@echo off",
            "timeout /t 3 /nobreak >nul",
            f'copy /y "{current}" "{backup}" >nul',
            f'copy /y "{staged}" "{current}" >nul',
            f'if errorlevel 1 copy /y "{backup}" "{current}" >nul',
            f'del /q "{staged}"',
            f'del /q "{pending}"',
            f'start "" "{current}"',
            "del /q \"%~f0\"",
        ]),
        encoding="utf-8",
    )
    subprocess.Popen(
        ["cmd", "/c", str(script)],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        close_fds=True,
    )
    return True
