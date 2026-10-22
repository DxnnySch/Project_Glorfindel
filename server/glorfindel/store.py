"""JSON-Ablage in OneDrive: atomar schreiben, weiche Sperren, Protokoll, Konfliktkopien."""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

LOCK_TTL_S = 120.0


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_json(path: Path, data: Any) -> None:
    """Atomar: erst temporär, dann ersetzen – OneDrive sieht nie halbe Dateien."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def log_change(gl_dir: Path, user: str, what: str) -> None:
    gl_dir.mkdir(parents=True, exist_ok=True)
    f = gl_dir / "log.jsonl"
    if f.exists() and what.endswith(" gespeichert"):  # Autosave zusammenfassen: gleiche Zeile nicht mehrfach in 10 Minuten
        try:
            last = json.loads(f.read_text(encoding="utf-8").splitlines()[-1])
            from datetime import datetime
            if last.get("was") == what and last.get("wer") == user and \
                    (datetime.fromisoformat(now_iso()) - datetime.fromisoformat(last["wann"])).total_seconds() < 600:
                return
        except Exception:  # noqa: BLE001
            pass
    line = json.dumps({"wer": user, "was": what, "wann": now_iso()}, ensure_ascii=False)
    with open(gl_dir / "log.jsonl", "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---- weiche Sperren ----
def _lock_file(locks_dir: Path, key: str) -> Path:
    return locks_dir / (re.sub(r"[^\w.-]", "_", key) + ".lock.json")


def acquire_lock(locks_dir: Path, key: str, user: str) -> dict:
    """Weiche Sperre: blockiert nie, meldet nur, wer gerade bearbeitet."""
    f = _lock_file(locks_dir, key)
    cur = read_json(f)
    if cur and cur.get("user") != user and time.time() - cur.get("ts", 0) < LOCK_TTL_S:
        return {"held": False, "by": cur["user"], "since": cur["ts"]}
    write_json(f, {"user": user, "ts": time.time()})
    return {"held": True, "by": user}


def release_lock(locks_dir: Path, key: str, user: str) -> None:
    f = _lock_file(locks_dir, key)
    cur = read_json(f)
    if cur and cur.get("user") == user:
        f.unlink(missing_ok=True)


def lock_status(locks_dir: Path, key: str) -> dict | None:
    cur = read_json(_lock_file(locks_dir, key))
    if cur and time.time() - cur.get("ts", 0) < LOCK_TTL_S:
        return cur
    return None


# ---- OneDrive-Konfliktkopien ----
_CONFLICT_RE = re.compile(r"^(?P<stem>.+)-(?P<pc>[A-Za-z0-9_]+)(?P<ext>\.json)$")


def find_conflicts(directory: Path) -> list[dict]:
    """Findet `sz_07-LAPTOP.json`, wenn `sz_07.json` existiert."""
    out = []
    for f in directory.glob("*.json"):
        m = _CONFLICT_RE.match(f.name)
        if m and (directory / (m["stem"] + m["ext"])).exists():
            out.append({"original": str(directory / (m["stem"] + m["ext"])), "copy": str(f), "pc": m["pc"]})
    return out
