"""Short-lived encrypted-at-rest-by-user-profile passport image staging."""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Irtifa" / "incoming"


def _safe_filename(value: str) -> str:
    name = Path(value).name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:100] or "passport.jpg"


def save_image(image_bytes: bytes, filename: str) -> Path:
    folder = ROOT / date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S_%f")
    target = folder / f"{stamp}_{_safe_filename(filename)}"
    target.write_bytes(image_bytes)
    return target


def cleanup_day(day: str | None = None) -> dict:
    target = ROOT / (day or date.today().isoformat())
    removed_files = 0
    if target.exists():
        for path in target.rglob("*"):
            if path.is_file():
                try:
                    path.unlink()
                    removed_files += 1
                except OSError:
                    pass
        try:
            target.rmdir()
        except OSError:
            pass
    return {"day": target.name, "removed_files": removed_files}


def cleanup_stale(days: int = 2) -> int:
    if not ROOT.exists():
        return 0
    cutoff = date.today() - timedelta(days=days)
    removed = 0
    for folder in ROOT.iterdir():
        if not folder.is_dir():
            continue
        try:
            folder_day = date.fromisoformat(folder.name)
        except ValueError:
            continue
        if folder_day < cutoff:
            removed += cleanup_day(folder.name)["removed_files"]
    return removed
