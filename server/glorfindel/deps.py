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
from .progress import Abgebrochen, Progress
from .progress import view as progress_view
from .service import Episode


class Jobs:
    """Hintergrundjobs mit detailliertem Fortschritt (siehe progress.py)."""

    def __init__(self, workers: int = 2):
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self.jobs: dict[str, dict] = {}
        self.lock = threading.Lock()

    def submit(self, name: str, fn, *args, **kw) -> str:
        jid = uuid.uuid4().hex[:10]
        job = {"id": jid, "name": name, "status": "laeuft", "result": None, "error": "", "started": time.time(), "finished": None}
        with self.lock:
            self.jobs[jid] = job
        progress = Progress(job)

        def run():
            try:
                job["result"] = fn(*args, progress=progress, **kw)
                for s in job.get("steps", []):
                    if s["status"] in ("läuft", "wartet"):
                        s.update(status="fertig" if s["status"] == "läuft" else "übersprungen", frac=1.0, finished=time.time())
                job["status"], job["detail"], job["sub"] = "fertig", "", None
            except Abgebrochen:
                job["status"], job["error"] = "abgebrochen", "Abgebrochen"
                for s in job.get("steps", []):
                    if s["status"] == "läuft":
                        s.update(status="abgebrochen", finished=time.time())
            except Exception as e:  # noqa: BLE001
                msg = str(e) or type(e).__name__
                job["status"], job["error"] = "fehler", msg if isinstance(e, (ValueError, FileNotFoundError, RuntimeError)) else f"{type(e).__name__}: {msg}"
                job["trace"] = traceback.format_exc()[-1500:]
                for s in job.get("steps", []):
                    if s["status"] == "läuft":
                        s.update(status="fehler", finished=time.time())
            finally:
                job["finished"] = time.time()

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
        return [progress_view(j) for j in items]

    def get(self, jid: str) -> dict:
        job = self.jobs.get(jid)
        if not job:
            raise HTTPException(404, "Job unbekannt")
        return progress_view(job)


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
