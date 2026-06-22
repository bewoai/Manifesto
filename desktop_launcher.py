"""Desktop entry point for the packaged Balon Manifesto app.

Starts the FastAPI server in the background, launches the Web UI in the default
web browser, and displays a native window control panel to manage the server process.
"""
from __future__ import annotations

import sys
import time
import threading
import webbrowser
import traceback
import multiprocessing
from pathlib import Path
import uvicorn

APP_URL = "http://127.0.0.1:8000/?v=desktop-20260623-1"


def _smoke_test() -> int:
    """Verify imports, configurations, and that static files are bundled."""
    from app import config
    from app.settings import load
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
    print("BalonManifesto smoke-test ok")
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
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
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

    try:
        import tkinter as tk
        from tkinter import ttk
    except ModuleNotFoundError:
        def open_browser_no_gui():
            time.sleep(1.5)
            webbrowser.open(APP_URL)

        threading.Thread(target=open_browser_no_gui, daemon=True).start()
        _run_server()
        return 0

    # Start FastAPI server in a background thread
    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    # Wait for server startup and open browser
    def open_browser():
        time.sleep(1.5)
        webbrowser.open(APP_URL)

    threading.Thread(target=open_browser, daemon=True).start()

    # Create a nice window control panel to exit the server gracefully
    root = tk.Tk()
    root.title("Balon Manifesto Sunucusu")
    root.geometry("420x240")
    root.resizable(False, False)

    # Styling matching the Turkish blue theme
    root.configure(background='#0a0e1a')
    style = ttk.Style()
    style.theme_use('clam')
    style.configure('TFrame', background='#0a0e1a')
    style.configure('TLabel', background='#0a0e1a', foreground='#f1f5f9')
    style.configure('TButton', background='#0077b6', foreground='#ffffff', borderwidth=0, font=('Helvetica', 10, 'bold'))
    style.map('TButton', background=[('active', '#005f8c')])

    frame = ttk.Frame(root, padding=20)
    frame.pack(fill=tk.BOTH, expand=True)

    title_label = ttk.Label(frame, text="🎈 Balon Manifesto Sunucusu", font=('Helvetica', 16, 'bold'), foreground='#00a8e8')
    title_label.pack(pady=(0, 10))

    status_label = ttk.Label(frame, text="Web sunucusu arka planda başarıyla başlatıldı.", font=('Helvetica', 10), foreground='#22c55e')
    status_label.pack(pady=5)

    info_label = ttk.Label(
        frame,
        text="Arayüze tarayıcınızdan aşağıdaki adresten erişebilirsiniz:\nhttp://127.0.0.1:8000",
        font=('Helvetica', 9),
        justify='center',
        foreground='#94a3b8'
    )
    info_label.pack(pady=10)

    btn_frame = ttk.Frame(frame)
    btn_frame.pack(pady=10)

    btn_open = ttk.Button(btn_frame, text="Tarayıcıda Aç", command=lambda: webbrowser.open("http://127.0.0.1:8000"))
    btn_open.pack(side=tk.LEFT, padx=10)

    btn_exit = ttk.Button(btn_frame, text="Durdur & Çıkış", command=root.destroy)
    btn_exit.pack(side=tk.LEFT, padx=10)

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
