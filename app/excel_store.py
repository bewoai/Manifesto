"""Safe, revision-aware access to the Excel planning workbook."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterator, TypeVar

import openpyxl


T = TypeVar("T")
LOCK_MAX_AGE_SECONDS = 10 * 60


class WorkbookConflictError(RuntimeError):
    pass


class WorkbookLockedError(RuntimeError):
    pass


def workbook_revision(path: Path) -> str:
    stat = path.stat()
    digest = hashlib.sha256()
    digest.update(str(stat.st_size).encode("ascii"))
    digest.update(str(stat.st_mtime_ns).encode("ascii"))
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:24]


def _lock_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.irtifa.lock")


@contextmanager
def workbook_lock(path: Path) -> Iterator[None]:
    lock_path = _lock_path(path)
    payload = {
        "pid": os.getpid(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "workbook": str(path),
    }
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > LOCK_MAX_AGE_SECONDS:
                    lock_path.unlink()
                    continue
            except OSError:
                pass
            raise WorkbookLockedError(
                "Planlama dosyası başka bir İrtifa işlemi tarafından kullanılıyor."
            )
    try:
        yield
    finally:
        try:
            lock_path.unlink()
        except OSError:
            pass


def backup_directory(path: Path) -> Path:
    target = path.parent / "Irtifa Yedekleri"
    target.mkdir(parents=True, exist_ok=True)
    return target


def create_backup(path: Path, *, reason: str = "write") -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_reason = "".join(ch for ch in reason if ch.isalnum() or ch in "-_")[:30]
    target = backup_directory(path) / f"{path.stem}_{stamp}_{safe_reason}.xlsx"
    shutil.copy2(path, target)
    return target


def cleanup_backups(path: Path, *, retention_days: int = 30) -> int:
    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = 0
    for candidate in backup_directory(path).glob(f"{path.stem}_*.xlsx"):
        try:
            if datetime.fromtimestamp(candidate.stat().st_mtime) < cutoff:
                candidate.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def list_backups(path: Path) -> list[dict]:
    rows = []
    for candidate in sorted(
        backup_directory(path).glob(f"{path.stem}_*.xlsx"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    ):
        stat = candidate.stat()
        rows.append({
            "name": candidate.name,
            "path": str(candidate),
            "size": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        })
    return rows


def _validate_workbook(path: Path) -> None:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=False)
    if not wb.sheetnames:
        wb.close()
        raise ValueError("Çalışma kitabında sayfa bulunamadı.")
    wb.close()


def atomic_update(
    path: Path,
    *,
    expected_revision: str | None,
    reason: str,
    mutator: Callable[[Path], T],
) -> tuple[T, str, Path]:
    """Run a workbook mutation against a temporary copy, then atomically replace."""
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(path)

    with workbook_lock(path):
        current_revision = workbook_revision(path)
        if expected_revision and expected_revision != current_revision:
            raise WorkbookConflictError(
                "Planlama dosyası başka bir kullanıcı tarafından değiştirildi. "
                "Günü yeniden yükleyip işlemi tekrar deneyin."
            )

        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.stem}_irtifa_",
            suffix=path.suffix,
            dir=str(path.parent),
        )
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            shutil.copy2(path, temp_path)
            result = mutator(temp_path)
            _validate_workbook(temp_path)
            backup = create_backup(path, reason=reason)
            os.replace(temp_path, path)
            cleanup_backups(path)
            return result, workbook_revision(path), backup
        finally:
            try:
                temp_path.unlink()
            except OSError:
                pass


def restore_backup(path: Path, backup_name: str) -> tuple[str, Path]:
    backup = (backup_directory(path) / backup_name).resolve()
    root = backup_directory(path).resolve()
    if root not in backup.parents or not backup.exists() or backup.suffix.lower() != ".xlsx":
        raise FileNotFoundError("Yedek bulunamadı.")

    with workbook_lock(path):
        current_backup = create_backup(path, reason="before_restore")
        fd, temp_name = tempfile.mkstemp(
            prefix=".irtifa_restore_",
            suffix=".xlsx",
            dir=str(path.parent),
        )
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            shutil.copy2(backup, temp_path)
            _validate_workbook(temp_path)
            os.replace(temp_path, path)
        finally:
            try:
                temp_path.unlink()
            except OSError:
                pass
    return workbook_revision(path), current_backup
