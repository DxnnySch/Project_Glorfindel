"""Bridge-Hub und WebSocket: simuliertes Panel (ohne Premiere)."""
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from glorfindel.api import create_app
from glorfindel.bridge import HUB, BridgeError, get_token
from glorfindel.config import Settings
from glorfindel.deps import AppState


@pytest.fixture
def client(tmp_path):
    HUB.ws, HUB.info = None, {}
    HUB._pending.clear()
    return TestClient(create_app(AppState(Settings(onedrive_root=str(tmp_path)), persist=False)), base_url="http://localhost")


def connect(c, token=None, headers=None):
    return c.websocket_connect(f"/api/bridge/ws?token={token if token is not None else get_token()}", headers=headers or {})


def hello(ws, premiere="26.5.2"):
    ws.send_text(json.dumps({"t": "hello", "info": {"premiere": premiere, "project": {"name": "Test.prproj", "path": "F:/x/Test.prproj"}}}))
    assert json.loads(ws.receive_text())["t"] == "welcome"


def call_async(op, args=None, timeout=10, on_event=None):
    box = {}

    def run():
        try:
            box["data"] = HUB.call(op, args, timeout=timeout, on_event=on_event)
        except Exception as e:  # noqa: BLE001
            box["err"] = e
    t = threading.Thread(target=run)
    t.start()
    return t, box


def test_pairing_token_is_stable_and_status_reports_disconnected(client):
    p = client.get("/api/bridge/pairing").json()
    assert p["token"] == get_token() == client.get("/api/bridge/pairing").json()["token"] and len(p["token"]) >= 20
    assert client.get("/api/bridge/status").json()["connected"] is False
    with pytest.raises(BridgeError, match="nicht verbunden"):
        HUB.call("ping")


def test_websocket_rejects_wrong_token_browser_origin_and_foreign_host(client):
    for kw in ({"token": "falsch"}, {"headers": {"origin": "http://evil.example"}}, {"headers": {"host": "evil.example"}}):
        with pytest.raises(WebSocketDisconnect):
            with connect(client, **kw) as ws:
                ws.receive_text()
    assert client.get("/api/bridge/status").json()["connected"] is False


def test_call_roundtrip_with_events_and_status(client):
    seen = []
    with connect(client) as ws:
        hello(ws)
        time.sleep(0.2)
        st = client.get("/api/bridge/status").json()
        assert st["connected"] and st["info"]["premiere"] == "26.5.2" and st["info"]["project"]["name"] == "Test.prproj"
        t, box = call_async("plan.run", {"steps": 3}, on_event=lambda n, d: seen.append((n, d)))
        msg = json.loads(ws.receive_text())
        assert msg["t"] == "call" and msg["op"] == "plan.run" and msg["args"] == {"steps": 3}
        ws.send_text(json.dumps({"t": "event", "id": msg["id"], "name": "progress", "data": {"done": 1, "of": 3}}))
        ws.send_text(json.dumps({"t": "event", "id": 0, "name": "log", "data": {"level": "warn", "text": "Effekt fehlt"}}))
        ws.send_text(json.dumps({"t": "result", "id": msg["id"], "ok": True, "data": {"built": 3}}))
        t.join(5)
        assert box.get("data") == {"built": 3} and seen == [("progress", {"done": 1, "of": 3})]
        assert any(e["text"] == "Effekt fehlt" and e["level"] == "warn" for e in client.get("/api/bridge/status").json()["log"])
    time.sleep(0.2)
    assert client.get("/api/bridge/status").json()["connected"] is False


def test_error_from_panel_and_unknown_op_and_disconnect_during_call(client):
    with connect(client) as ws:
        hello(ws)
        t, box = call_async("media.swap", {})
        msg = json.loads(ws.receive_text())
        ws.send_text(json.dumps({"t": "result", "id": msg["id"], "ok": False, "error": "Medium nicht gefunden"}))
        t.join(5)
        assert "Medium nicht gefunden" in str(box["err"])
        with pytest.raises(BridgeError, match="Unbekannte"):
            HUB.call("rm -rf")
        t, box = call_async("project.dump")
        ws.receive_text()
    t.join(5)                                                     # Trennung beendet wartende Aufrufe sofort
    assert "getrennt" in str(box["err"])


def test_rest_call_only_allows_diagnostic_ops(client):
    assert client.post("/api/bridge/call", json={"op": "plan.run"}).status_code == 400
    assert client.post("/api/bridge/call", json={"op": "ping"}).status_code == 409          # nicht verbunden
    with connect(client) as ws:
        hello(ws)
        holder = {}
        t = threading.Thread(target=lambda: holder.update(r=client.post("/api/bridge/call", json={"op": "ping"})))
        t.start()
        msg = json.loads(ws.receive_text())
        ws.send_text(json.dumps({"t": "result", "id": msg["id"], "ok": True, "data": {"pong": True}}))
        t.join(5)
        assert holder["r"].json() == {"data": {"pong": True}}


def test_new_panel_replaces_old_one(client):
    with connect(client) as a:
        hello(a, "26.5.1")
        with connect(client) as b:
            hello(b, "26.5.2")
            time.sleep(0.2)
            assert client.get("/api/bridge/status").json()["info"]["premiere"] == "26.5.2"
