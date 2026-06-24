"""Desktop entry point for the packaged İrtifa app.

Starts the FastAPI server in the background and hosts the Web UI in a native
WebView window. Closing the window exits the whole app.
"""
from __future__ import annotations

import os
import socket
import sys
import time
import threading
import urllib.request
import traceback
import multiprocessing
from pathlib import Path
import uvicorn
from app.version import APP_VERSION

APP_HOST = "127.0.0.1"
APP_PORT = int(os.environ.get("BALON_MANIFESTO_PORT") or "0")


def _choose_port() -> int:
    if APP_PORT:
        return APP_PORT
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((APP_HOST, 0))
        return int(s.getsockname()[1])


PORT = _choose_port()
APP_URL = f"http://{APP_HOST}:{PORT}/?v={APP_VERSION}"
HEALTH_URL = f"http://{APP_HOST}:{PORT}/health"


def _wait_for_server(timeout_seconds: float = 25) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=1) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def _shutdown_process() -> None:
    os._exit(0)


def _smoke_test() -> int:
    """Verify imports, configurations, and that static files are bundled."""
    from app import config
    from app.settings import load
    import webview  # noqa: F401
    import googleapiclient.discovery  # noqa: F401
    import google.oauth2.service_account  # noqa: F401
    from app.main import app  # noqa: F401

    # Verify data files exist
    missing = [
        str(path)
        for path in (config.COUNTRY_MAP_PATH, config.MANIFEST_TEMPLATE_PATH)
        if not Path(path).exists()
    ]
    if missing:
        print("missing bundled files:")
        for item in missing:
            print(f"  {item}")
        return 2

    # Verify frontend static assets exist
    dist_path = Path(__file__).resolve().parent / "frontend" / "dist"
    if not dist_path.exists():
        print(f"missing frontend static files in: {dist_path}")
        return 3

    load()
    print("Irtifa smoke-test ok")
    return 0


def _run_server():
    """Start the FastAPI server using Uvicorn and handle log redirection."""
    # Redirect stdout/stderr to prevent silent consoleless PyInstaller crashes
    log_dir = Path.home() / ".manifesto"
    log_dir.mkdir(parents=True, exist_ok=True)
    server_log = log_dir / "server.log"
    crash_log = log_dir / "crash.log"

    try:
        class FileLogger:
            def __init__(self, filepath: Path):
                self.file = open(filepath, "a", encoding="utf-8")
            def write(self, text):
                self.file.write(text)
                self.file.flush()
            def flush(self):
                self.file.flush()
            def isatty(self):
                return False
            def __getattr__(self, name):
                return getattr(self.file, name)

        logger = FileLogger(server_log)
        sys.stdout = logger
        sys.stderr = logger

        print(f"\n--- Server starting at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
        from app.main import app
        uvicorn.run(app, host=APP_HOST, port=PORT, log_level="info")
    except Exception as e:
        with open(crash_log, "w", encoding="utf-8") as f:
            f.write(f"Crash at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Error: {e}\n")
            f.write(traceback.format_exc())
        raise


def main() -> int:
    multiprocessing.freeze_support()

    if "--smoke-test" in sys.argv:
        return _smoke_test()

    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()
    if not _wait_for_server():
        raise RuntimeError("İrtifa yerel sunucusu başlatılamadı.")

    try:
        import webview
    except ModuleNotFoundError as exc:
        raise RuntimeError("WebView bileşeni bulunamadı. pywebview kurulmalı.") from exc

    webview.create_window(
        "İrtifa",
        APP_URL,
        width=1360,
        height=860,
        min_size=(1100, 720),
        text_select=True,
        confirm_close=False,
        background_color="#181225",
    )
    webview.start(
        gui="edgechromium",
        private_mode=False,
        storage_path=str(Path.home() / ".manifesto" / "webview"),
    )
    _shutdown_process()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
