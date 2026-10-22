"""Welle 1: Jobs abbrechen/auflisten, Papierkorb, Status veraltet, Versionsschutz, Cockpit."""
import time

from fastapi.testclient import TestClient

from glorfindel.api import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("GLORFINDEL_HOME", str(tmp_path / "home"))
    root = tmp_path / "od"
    (root / "Mythen-Archiv/Videos").mkdir(parents=True)
    c = TestClient(create_app())
    s = c.get("/api/settings").json()
    s.update(onedrive_root=str(root), user="anna")
    c.put("/api/settings", json=s)
    c.post("/api/episodes", json={"season": 2, "episode": 1})
    return c


def _scene(c, **kw):
    r = c.post("/api/ep/2/1/scenes", json={"titel": "A", "segmente": [{"in": 1, "out": 5}], "kommentar": [{"sprecher": "philipp", "text": "Hallo Welt"}], **kw})
    return r.json()


def test_jobs_list_and_cancel(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    state = c.app.state.gl

    def slow(progress):
        for i in range(100):
            time.sleep(0.02)
            progress(i / 100)
    jid = state.jobs.submit("langsam", slow)
    assert any(j["id"] == jid for j in c.get("/api/jobs").json())
    c.post(f"/api/jobs/{jid}/cancel")
    for _ in range(50):
        if c.get(f"/api/jobs/{jid}").json()["status"] != "laeuft":
            break
        time.sleep(0.05)
    assert c.get(f"/api/jobs/{jid}").json()["status"] == "abgebrochen"


def test_trash_and_restore(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    sc = _scene(c)
    assert c.delete(f"/api/ep/2/1/scenes/{sc['id']}").status_code == 200
    assert c.get("/api/ep/2/1/scenes").json() == []
    assert c.post(f"/api/ep/2/1/scenes/{sc['id']}/restore").status_code == 200
    assert len(c.get("/api/ep/2/1/scenes").json()) == 1
    assert c.post("/api/ep/2/1/scenes/sz_99/restore").status_code == 404


def test_status_becomes_stale_when_text_changes(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    sc = _scene(c, status="abgeglichen")
    sc = c.get("/api/ep/2/1/scenes").json()[0]
    sc["status"] = "abgeglichen"
    for k in ("report", "lock", "problems"):
        sc.pop(k, None)
    c.put(f"/api/ep/2/1/scenes/{sc['id']}", json=sc)  # keine inhaltliche Änderung -> bleibt
    again = c.get("/api/ep/2/1/scenes").json()[0]
    assert again["status"] == "abgeglichen"
    again["kommentar"][0]["text"] = "Ganz anderer Text"
    for k in ("report", "lock", "problems"):
        again.pop(k, None)
    r = c.put(f"/api/ep/2/1/scenes/{sc['id']}", json=again).json()
    assert r["scene"]["status"] == "veraltet"


def test_version_guard(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    sc = _scene(c)
    full = c.get("/api/ep/2/1/scenes").json()[0]
    for k in ("report", "lock", "problems"):
        full.pop(k, None)
    # Andere Person hat inzwischen gespeichert
    st = c.app.state.gl
    ep = st.episode(2, 1)
    other = ep.scenes()[0]
    other.titel = "von Bob"
    st.settings.user = "bob"
    ep.settings = st.settings
    ep.save_scene(other)
    st.settings.user = "anna"
    r = c.put(f"/api/ep/2/1/scenes/{sc['id']}?base=2000-01-01T00:00:00", json=full)
    assert r.status_code == 409 and "bob" in r.json()["detail"]


def test_cockpit(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    c.post("/api/ep/2/1/scenes", json={"titel": "leer"})
    d = c.get("/api/ep/2/1/cockpit").json()
    texts = " ".join(t["text"] for t in d["tasks"])
    assert "Referenz" in texts and "ohne Serienmaterial" in texts
    assert d["phases"]["vorbereiten"] is False
