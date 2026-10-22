"""Starter: `python -m glorfindel` startet den lokalen Server und öffnet den Browser."""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser


def _cuda_dll_dirs() -> None:
    """Unter Windows die per pip installierten CUDA-Bibliotheken (cuBLAS/cuDNN) auffindbar machen."""
    if sys.platform != "win32":
        return
    from pathlib import Path
    site = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for sub in ("cublas", "cudnn"):
        d = site / sub / "bin"
        if d.exists():
            os.add_dll_directory(str(d))
            os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")


def free_port(preferred: int) -> int:
    for p in range(preferred, preferred + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise RuntimeError("Kein freier Port gefunden")


def main() -> None:
    ap = argparse.ArgumentParser(prog="glorfindel")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    _cuda_dll_dirs()
    import uvicorn
    from .api import create_app
    port = free_port(args.port)
    url = f"http://localhost:{port}"
    if not args.no_browser:
        threading.Thread(target=lambda: (time.sleep(1.2), webbrowser.open(url)), daemon=True).start()
    print(f"Projekt Glorfindel läuft auf {url}  (Beenden: Strg+C)")
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
