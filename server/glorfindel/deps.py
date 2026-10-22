"""Gemeinsamer Zustand der API: Einstellungen, Folgen-Zugriff, Hintergrundjobs."""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import HTTPException

from .config import Settings, load_settings, save_settings
from .service import Episode


class Abgebrochen(Exception):
    """Auftrag wurde vom Nutzer abgebrochen."""


class Jobs:
    """Einfache Hintergrundjobs mit Fortschritt (Proxys, Transkription, Conform …)."""

    def __init__(self, workers: int = 2):
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self.jobs: dict[str, dict] = {}
        self.lock = threading.Lock()

    def submit(self, name: str, fn, *args, **kw) -> str:
        jid = uuid.uuid4().hex[:10]
        job = {"id": jid, "name": name, "status": "laeuft", "progress": 0.0, "result": None, "error": "",
               "started": time.time()}
        with self.lock:
            self.jobs[jid] = job

        def progress(p: float) -> None:
            if job.get("cancel"):
                raise Abgebrochen("Abgebrochen")
            job["progress"] = round(min(1.0, max(0.0, p)), 3)

        def run():
            try:
                job["result"] = fn(*args, progress=progress, **kw)
                job["status"], job["progress"] = "fertig", 1.0
            except Abgebrochen:
                job["status"], job["error"] = "abgebrochen", "Abgebrochen"
            except Exception as e:  # noqa: BLE001
                msg = str(e) or type(e).__name__
                job["status"], job["error"] = "fehler", msg if isinstance(e, (ValueError, FileNotFoundError, RuntimeError)) else f"{type(e).__name__}: {msg}"
                job["trace"] = traceback.format_exc()[-1500:]

        self.pool.submit(run)
        return jid

    def cancel(self, jid: str) -> dict:
        job = self.jobs.get(jid)
        if not job:
            raise HTTPException(404, "Job unbekannt")
        if job["status"] == "laeuft":
            job["cancel"] = True
        return self.get(jid)

    def list(self, limit: int = 30) -> list[dict]:
        items = sorted(self.jobs.values(), key=lambda j: j["started"], reverse=True)[:limit]
        return [{k: v for k, v in j.items() if k != "trace"} for j in items]

    def get(self, jid: str) -> dict:
        job = self.jobs.get(jid)
        if not job:
            raise HTTPException(404, "Job unbekannt")
        return {k: v for k, v in job.items() if k != "trace"}


class AppState:
    def __init__(self, settings: Settings | None = None, persist: bool = True):
        self.settings = settings or load_settings()
        self.persist = persist
        self.jobs = Jobs()
        self._llm = None

    def save(self) -> None:
        if self.persist:
            save_settings(self.settings)
        self._llm = None

    def llm(self):
        from .llm import Llm
        if self._llm is None:
            self._llm = Llm(self.settings)
        return self._llm

    def episode(self, season: int, episode: int, must_exist: bool = True) -> Episode:
        if not self.settings.onedrive_root or not Path(self.settings.onedrive_root).is_dir():
            raise HTTPException(409, "OneDrive-Stammordner ist nicht gesetzt (Einstellungen).")
        ep = Episode(self.settings, season, episode)
        if must_exist and not ep.exists():
            raise HTTPException(404, f"Folge S{season} E{episode} existiert nicht")
        return ep

    def templates_dir(self) -> Path:
        """Vorlagenordner in OneDrive (falls vorhanden), sonst die mitgelieferten Vorlagen."""
        d = Path(self.settings.onedrive_root) / self.settings.templates_dir
        return d if (d / "rohschnitt_vorlage.json").exists() else Path(__file__).resolve().parents[2] / "vorlagen"
