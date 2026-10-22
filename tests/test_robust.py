"""Regressionen aus dem Nutzer-Review: Rohschnitt-Robustheit, Fehlertexte, Validierung."""
from fastapi.testclient import TestClient

from glorfindel.api import create_app
from glorfindel.deps import AppState
from glorfindel.config import Settings
from glorfindel.rough_cut import build_package
from glorfindel.models import Scene, CommentBlock, Segment
from glorfindel.config import Thresholds


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("GLORFINDEL_HOME", str(tmp_path / "home"))
    root = tmp_path / "od"
    (root / "Mythen-Archiv/Videos").mkdir(parents=True)
    c = TestClient(create_app())
    s = c.get("/api/settings").json()
    s["onedrive_root"] = str(root)
    c.put("/api/settings", json=s)
    return c


def test_rough_cut_handles_missing_alignment_entry():
    sc = [Scene(id="sz_01", titel="A", segmente=[Segment(**{"in": 0, "out": 5})], kommentar=[CommentBlock(text="Hallo Welt hier")])]
    tpl = None
    from glorfindel.rough_cut import load_template
    pkg = build_package(sc, slug="S", template=load_template(None), th=Thresholds(),
                        alignment={"recordings": [], "scenes": {"sz_01": [{"block": 0, "rec": "r1", "missing": True}]}})
    assert any("keine Aufnahme" in w for w in pkg["warnings"])


def test_scene_without_segment_warns():
    sc = [Scene(id="sz_01", titel="Leer")]
    from glorfindel.rough_cut import load_template
    pkg = build_package(sc, slug="S", template=load_template(None), th=Thresholds())
    assert any("Serienmaterial" in w for w in pkg["warnings"])


def test_episode_validation_and_duplicates(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.post("/api/episodes", json={"season": 0, "episode": 1}).status_code == 400
    assert c.post("/api/episodes", json={"season": 2, "episode": 1}).status_code == 200
    r = c.post("/api/episodes", json={"season": 2, "episode": 1})
    assert r.status_code == 409 and "gibt es schon" in r.json()["detail"]


def test_friendly_errors(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    c.post("/api/episodes", json={"season": 2, "episode": 1})
    assert c.post("/api/ep/2/1/sources", json={"path": "/nicht/da.mp4"}).status_code == 404
    assert c.post("/api/ep/2/1/recording", json={"path": "/nicht/da.wav", "speaker": "philipp"}).status_code == 404
    assert c.post("/api/ep/2/1/scenes", json={"kommentar": [{"sprecher": "hans", "text": "x"}]}).status_code == 400
    bad = c.post("/api/ep/2/1/script/import-preview", files={"file": ("x.docx", b"kein word", "application/octet-stream")})
    assert bad.status_code == 400 and "Word" in bad.json()["detail"]


def test_auto_transcription_never_uses_cloud():
    from glorfindel import stt
    assert stt.choose_backend("auto") in ("lokal", "keins")
