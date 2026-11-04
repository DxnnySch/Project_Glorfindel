"""Werkzeuge im Panel: Anfragen über die Bridge (simuliertes Panel) und „Szene in Premiere zeigen“."""
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from glorfindel import premiere_ops, premiere_tools
from glorfindel.api import create_app
from glorfindel.bridge import HUB, get_token
from glorfindel.deps import AppState
from test_premiere_ops import FakeHub, ep  # noqa: F401 – Fixtures

TEMPLATES = Path(__file__).resolve().parents[1] / "vorlagen"


@pytest.fixture
def built(ep):  # noqa: F811
    premiere_ops.build_in_premiere(ep, TEMPLATES, hub=FakeHub())
    return ep


def rpc(ws, method, args=None, rid=1):
    ws.send_text(json.dumps({"t": "rpc", "id": rid, "method": method, "args": args or {}}))
    while True:
        msg = json.loads(ws.receive_text())
        if msg.get("t") == "rpc_result":
            assert msg["id"] == rid
            return msg


def client_for(ep):  # noqa: F811
    HUB.ws, HUB.info = None, {}
    HUB._pending.clear()
    return TestClient(create_app(AppState(ep.settings, persist=False)), base_url="http://localhost")


def test_build_remembers_the_episode_for_the_tools(built):
    assert json.loads(premiere_tools.context_path().read_text(encoding="utf-8")) == {"season": 3, "episode": 1}


def test_panel_rpc_roundtrip_config_effects_scene(built):
    c = client_for(built)
    with c.websocket_connect(f"/api/bridge/ws?token={get_token()}") as ws:
        ws.send_text(json.dumps({"t": "hello", "info": {"premiere": "27.1.0"}}))
        assert json.loads(ws.receive_text())["t"] == "welcome"
        cfg = rpc(ws, "tools.config")
        assert cfg["ok"] and any(e["id"] == "karte" for e in cfg["data"]["effekte"]) and {a["art"] for a in cfg["data"]["credits"]} == {"amazon", "artwork", "musik"}
        eff = rpc(ws, "tools.effects", {"ids": ["karte_in"], "clips": [{"dur": 5.0}]}, rid=2)
        assert eff["ok"] and eff["data"]["clips"][0][0]["id"] == "karte_in"
        sc = rpc(ws, "tools.scene_at", {"time": 0.5}, rid=3)
        assert sc["ok"] and sc["data"]["scene"].startswith("sz_") and sc["data"]["titel"] == "Schmiede"
        bad = rpc(ws, "tools.rm_rf", {}, rid=4)
        assert bad["ok"] is False and "Unbekannte Methode" in bad["error"]
        err = rpc(ws, "tools.effects", {"ids": ["gibt_es_nicht"], "clips": [{"dur": 1}]}, rid=5)
        assert err["ok"] is False and "unbekannt" in err["error"]
        again = rpc(ws, "tools.config", rid=6)
        assert again["ok"]                                                        # Verbindung bleibt nach Fehlern nutzbar
    time.sleep(0.1)


def test_rpc_without_a_built_episode_explains_what_to_do(ep):  # noqa: F811
    c = client_for(ep)
    with c.websocket_connect(f"/api/bridge/ws?token={get_token()}") as ws:
        ws.send_text(json.dumps({"t": "hello", "info": {}}))
        ws.receive_text()
        r = rpc(ws, "tools.config")
        assert r["ok"] is False and "Rohschnitt bauen" in r["error"]


def test_show_scene_sets_the_playhead_to_the_scene_start(built):
    hub = FakeHub()
    plan = json.loads((premiere_ops.pdir(built) / f"bauplan_v{premiere_ops.load_state(built)['version']}.json").read_text(encoding="utf-8"))
    sid = next(c["scene"] for c in plan["clips"] if c["kind"] == "episode")
    want = min(c["start"] for c in plan["clips"] if c.get("scene") == sid)
    out = premiere_ops.show_scene(built, sid, hub=hub)
    assert hub.calls[-1] == ("sequence.seek", {"time": want}) and out["time"] == want
    with pytest.raises(ValueError, match="nicht im Rohschnitt"):
        premiere_ops.show_scene(built, "sz_99", hub=hub)
    c = client_for(built)
    assert c.post("/api/ep/3/1/premiere/show-scene", json={"scene": "sz_99"}).status_code == 400
    assert c.post(f"/api/ep/3/1/premiere/show-scene", json={"scene": sid}).status_code == 409        # Panel nicht verbunden
