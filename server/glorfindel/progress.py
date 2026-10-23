"""Detaillierter Fortschritt für Hintergrundaufträge: Schritte, Teilschritte, Dauer, Restzeit.

Ein `Progress` bleibt als Funktion aufrufbar (`progress(0.5)` wie bisher), kann aber zusätzlich:
- `plan([...])`: alle Schritte vorab nennen (Name oder (Name, Gewicht)); Gewichte steuern die Gesamtprozent.
- `step(name_oder_index, detail)`: nächsten Schritt beginnen (vorherige gelten als fertig).
- `sub(done, total, detail, unit)`: Teilfortschritt im aktuellen Schritt („3 von 12 Standbildern“).
- `fraction(f, detail)`: Anteil des aktuellen Schritts (0..1) ohne Zählung, z. B. bei ffmpeg.
"""
from __future__ import annotations

import time
from typing import Callable


class Abgebrochen(Exception):
    """Auftrag wurde vom Nutzer abgebrochen."""


class Progress:
    def __init__(self, job: dict):
        self.job = job
        job.setdefault("steps", [])
        job.setdefault("step_index", 0)
        job.setdefault("detail", "")
        job.setdefault("sub", None)
        job["_fixed"] = None  # Gesamtanteil ohne Plan (klassischer Aufruf)

    # ---- Abbruch ----
    def check(self) -> None:
        if self.job.get("cancel"):
            raise Abgebrochen("Abgebrochen")

    # ---- klassisch ----
    def __call__(self, p: float, detail: str | None = None) -> None:
        self.check()
        if self.job["steps"]:
            self.fraction(p, detail)
        else:
            self.job["_fixed"] = min(1.0, max(0.0, p))
            if detail is not None:
                self.job["detail"] = detail

    # ---- Plan / Schritte ----
    def plan(self, steps: list) -> "Progress":
        self.job["steps"] = [{"name": s if isinstance(s, str) else s[0], "weight": 1.0 if isinstance(s, str) else float(s[1]),
                              "status": "wartet", "frac": 0.0, "started": None, "finished": None, "detail": ""} for s in steps]
        self.job["step_index"] = 0
        return self

    def add_steps(self, steps: list, before_last: int = 0) -> None:
        """Weitere Schritte anhängen, wenn sie erst unterwegs bekannt werden (z. B. je Aufnahme)."""
        for s in steps:
            self.job["steps"].append({"name": s if isinstance(s, str) else s[0], "weight": 1.0 if isinstance(s, str) else float(s[1]),
                                      "status": "wartet", "frac": 0.0, "started": None, "finished": None, "detail": ""})

    def _cur(self) -> dict | None:
        i = self.job["step_index"]
        return self.job["steps"][i - 1] if 1 <= i <= len(self.job["steps"]) else None

    def step(self, which, detail: str = "") -> None:
        self.check()
        steps = self.job["steps"]
        if isinstance(which, str):
            idx = next((k for k, s in enumerate(steps) if s["name"] == which), None)
            if idx is None:
                steps.append({"name": which, "weight": 1.0, "status": "wartet", "frac": 0.0, "started": None, "finished": None, "detail": ""})
                idx = len(steps) - 1
        else:
            idx = which
        now = time.time()
        for k, s in enumerate(steps):
            if k < idx and s["status"] != "fertig":
                s.update(status="fertig", frac=1.0, finished=s["finished"] or now, started=s["started"] or now)
        s = steps[idx]
        s.update(status="läuft", started=now, finished=None, frac=0.0, detail=detail)
        self.job["step_index"] = idx + 1
        self.job["detail"] = detail
        self.job["sub"] = None

    def finish_step(self) -> None:
        s = self._cur()
        if s:
            s.update(status="fertig", frac=1.0, finished=time.time())

    def skip(self, which, detail: str = "übersprungen") -> None:
        steps = self.job["steps"]
        idx = which if isinstance(which, int) else next((k for k, s in enumerate(steps) if s["name"] == which), None)
        if idx is not None:
            steps[idx].update(status="übersprungen", frac=1.0, detail=detail, finished=time.time())

    def detail(self, text: str) -> None:
        self.check()
        self.job["detail"] = text
        s = self._cur()
        if s:
            s["detail"] = text

    def fraction(self, f: float, detail: str | None = None) -> None:
        self.check()
        s = self._cur()
        if s is None:
            self.job["_fixed"] = min(1.0, max(0.0, f))
        else:
            s["frac"] = min(1.0, max(0.0, f))
        if detail is not None:
            self.detail(detail)

    def sub(self, done: float, total: float, detail: str = "", unit: str = "") -> None:
        self.check()
        s = self._cur()
        frac = (done / total) if total else 0.0
        self.job["sub"] = {"done": done, "total": total, "unit": unit, "since": (self.job["sub"] or {}).get("since") or time.time()}
        if s is not None:
            s["frac"] = min(1.0, max(0.0, frac))
        else:
            self.job["_fixed"] = min(1.0, max(0.0, frac))
        if detail:
            self.detail(detail)

    def callback(self, detail_fn: Callable[[float], str] | None = None) -> Callable[[float, str | None], None]:
        """Für Bibliotheken mit `progress_cb(fraction)`: setzt den Anteil des aktuellen Schritts."""
        def cb(f: float, detail: str | None = None) -> None:
            self.fraction(f, detail if detail is not None else (detail_fn(f) if detail_fn else None))
        return cb


def overall(job: dict) -> float:
    steps = job.get("steps") or []
    if not steps:
        return job["_fixed"] if job.get("_fixed") is not None else 0.0
    total = sum(s["weight"] for s in steps) or 1.0
    done = sum(s["weight"] * (1.0 if s["status"] in ("fertig", "übersprungen") else s["frac"] if s["status"] == "läuft" else 0.0) for s in steps)
    return min(1.0, done / total)


def view(job: dict, now: float | None = None) -> dict:
    """Öffentliche Sicht mit Laufzeit, Restzeit und Schrittliste (ohne interne Felder)."""
    now = now or time.time()
    running = job["status"] == "laeuft"
    end = now if running else (job.get("finished") or now)
    elapsed = max(0.0, end - job["started"])
    f = 1.0 if job["status"] == "fertig" else overall(job)
    eta = None
    if running and f >= 0.03 and elapsed >= 2.0:
        eta = elapsed * (1 - f) / f
    cur = None
    steps = job.get("steps") or []
    idx = job.get("step_index", 0)
    step_eta = step_elapsed = None
    if 1 <= idx <= len(steps):
        cur = steps[idx - 1]
        if cur["started"]:
            step_elapsed = max(0.0, (now if cur["status"] == "läuft" else (cur["finished"] or now)) - cur["started"])
            if cur["status"] == "läuft" and cur["frac"] >= 0.03 and step_elapsed >= 1.5:
                step_eta = step_elapsed * (1 - cur["frac"]) / cur["frac"]
    out = {k: v for k, v in job.items() if k not in ("trace", "_fixed", "cancel", "steps")}
    out.update(progress=round(f, 4), elapsed=round(elapsed, 1), eta=None if eta is None else round(eta, 1),
               step_index=idx, step_total=len(steps), step_name=cur["name"] if cur else "", step_elapsed=None if step_elapsed is None else round(step_elapsed, 1),
               step_eta=None if step_eta is None else round(step_eta, 1), step_fraction=round(cur["frac"], 4) if cur else None,
               cancelling=bool(job.get("cancel")) and running,
               steps=[{"name": s["name"], "status": s["status"], "frac": round(s["frac"], 3), "detail": s["detail"],
                       "seconds": None if not s["started"] else round(((s["finished"] or now) - s["started"]), 1)} for s in steps])
    return out


def as_progress(p) -> Progress:
    """Beliebigen Aufrufer (None, Funktion, Progress) in ein Progress verwandeln, damit Code ohne Auftrag weiterläuft."""
    if isinstance(p, Progress):
        return p
    q = Progress({"status": "laeuft", "started": time.time(), "finished": None})
    if callable(p):
        q.job["_legacy"] = p
        orig = q.__class__.fraction

        def hook(self, f, detail=None, _o=orig):  # noqa: ANN001
            _o(self, f, detail)
            try:
                p(overall(self.job))
            except TypeError:
                pass
        q.fraction = hook.__get__(q)  # type: ignore[method-assign]
    return q
