"""Premiere-Bridge: Verbindung zwischen dem App-Server und dem UXP-Panel in Premiere Pro.

Das Panel verbindet sich per WebSocket (127.0.0.1). Der Server schickt benannte Operationen (`call`), das Panel antwortet mit
Ergebnis oder Fehler und meldet Fortschritt/Log als Ereignisse. Es ist immer höchstens ein Panel verbunden.
"""
from __future__ import annotations

import asyncio
import collections
import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .config import app_dir

PROTOCOL = 1
# Operationen, die der Server aufrufen darf (das Panel akzeptiert ebenfalls nur diese)
OPS = {"ping", "info", "introspect", "selftest", "project.dump", "sequence.dump", "plan.run", "media.swap", "media.refresh",
       "project.save", "template.inspect", "probe.bin", "probe.place", "probe.swap"}


class BridgeError(RuntimeError):
    """Fehler der Bridge (nicht verbunden, Zeitüberschreitung, Fehler im Panel)."""


def token_path() -> Path:
    return app_dir() / "bridge_token.txt"


def get_token() -> str:
    """Pairing-Token: einmal erzeugt, lokal gespeichert (nie in OneDrive)."""
    p = token_path()
    if p.exists() and p.read_text(encoding="utf-8").strip():
        return p.read_text(encoding="utf-8").strip()
    t = secrets.token_urlsafe(24)
    p.write_text(t, encoding="utf-8")
    return t


class BridgeHub:
    def __init__(self) -> None:
        self.ws: Any = None
        self.info: dict = {}
        self.connected_at = 0.0
        self.loop: asyncio.AbstractEventLoop | None = None
        self._pending: dict[int, dict] = {}
        self._next = 1
        self._lock = threading.Lock()
        self.log: collections.deque = collections.deque(maxlen=400)

    # ---------- Status ----------
    @property
    def connected(self) -> bool:
        return self.ws is not None

    def status(self) -> dict:
        return {"connected": self.connected, "info": self.info, "since": self.connected_at if self.connected else None,
                "protocol": PROTOCOL, "log": list(self.log)[-60:]}

    def _log(self, level: str, text: str) -> None:
        self.log.append({"t": time.time(), "level": level, "text": text})

    # ---------- Verbindung (vom WebSocket-Endpunkt aufgerufen) ----------
    async def serve(self, ws) -> None:
        """Läuft solange das Panel verbunden ist. `ws`: Starlette-WebSocket, bereits akzeptiert und authentifiziert."""
        if self.ws is not None:                    # neues Panel ersetzt ein altes (z. B. nach Neuladen des Plugins)
            try:
                await self.ws.close(code=4000)
            except Exception:  # noqa: BLE001
                pass
            self._fail_all("Panel hat sich neu verbunden")
        self.loop = asyncio.get_running_loop()
        self.ws, self.connected_at = ws, time.time()
        try:
            hello = json.loads(await asyncio.wait_for(ws.receive_text(), 15))
            self.info = hello.get("info", {}) if hello.get("t") == "hello" else {}
            await ws.send_text(json.dumps({"t": "welcome", "protocol": PROTOCOL}))
            self._log("info", f"Premiere verbunden: {self.info.get('premiere', '?')} · Projekt {self.info.get('project', {}).get('name', '–')}")
            while True:
                msg = json.loads(await ws.receive_text())
                self._on_message(msg)
        except Exception as e:  # noqa: BLE001 – Trennung, Zeitüberschreitung, ungültiges JSON
            self._log("info", f"Verbindung beendet ({type(e).__name__})")
        finally:
            if self.ws is ws:
                self.ws, self.info = None, {}
            self._fail_all("Verbindung zu Premiere getrennt")

    def _on_message(self, msg: dict) -> None:
        t = msg.get("t")
        if t == "result":
            slot = self._pending.get(msg.get("id"))
            if slot:
                slot["result"] = msg
                slot["tevent"].set()
        elif t == "event":
            slot = self._pending.get(msg.get("id"))
            if msg.get("name") == "log":
                self._log(msg.get("data", {}).get("level", "info"), str(msg.get("data", {}).get("text", "")))
            elif slot and slot.get("on_event"):
                try:
                    slot["on_event"](msg.get("name"), msg.get("data"))
                except Exception:  # noqa: BLE001
                    pass
        elif t == "info":
            self.info.update(msg.get("info", {}))

    def _fail_all(self, why: str) -> None:
        for slot in list(self._pending.values()):
            slot["result"] = {"ok": False, "error": why}
            slot["tevent"].set()

    # ---------- Aufruf aus Arbeits-Threads (Jobs, REST) ----------
    def call(self, op: str, args: dict | None = None, timeout: float = 60.0,
             on_event: Callable[[str, Any], None] | None = None) -> Any:
        if op not in OPS:
            raise BridgeError(f"Unbekannte Operation: {op}")
        if not self.connected or self.loop is None:
            raise BridgeError("Premiere ist nicht verbunden. Panel „Glorfindel Bridge“ in Premiere öffnen.")
        with self._lock:
            cid, self._next = self._next, self._next + 1
        slot = {"tevent": threading.Event(), "result": None, "on_event": on_event}
        self._pending[cid] = slot
        payload = json.dumps({"t": "call", "id": cid, "op": op, "args": args or {}})
        ws = self.ws
        fut = asyncio.run_coroutine_threadsafe(ws.send_text(payload), self.loop)
        try:
            fut.result(10)
            if not slot["tevent"].wait(timeout):
                raise BridgeError(f"Premiere hat nicht rechtzeitig geantwortet ({op}, {timeout:.0f} s)")
        finally:
            self._pending.pop(cid, None)
        res = slot["result"] or {}
        if not res.get("ok"):
            raise BridgeError(res.get("error") or "Unbekannter Fehler in Premiere")
        return res.get("data")


HUB = BridgeHub()
