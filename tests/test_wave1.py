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


def test_free_blocks_and_take_choice(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    sc = _scene(c)
    assert c.put("/api/ep/2/1/free-blocks", json=[{"titel": "Werbung", "after": sc["id"], "dauer": 81}]).status_code == 200
    assert c.get("/api/ep/2/1/free-blocks").json()[0]["dauer"] == 81
    assert c.put("/api/ep/2/1/free-blocks", json=[{"titel": "X", "after": "sz_99"}]).status_code == 400
    ep = c.app.state.gl.episode(2, 1)
    from glorfindel import pipeline
    pipeline.save_alignment(ep, {"recordings": [], "scenes": {sc["id"]: [{"block": 0, "rec": "r", "in": 1, "out": 2, "takes": [{"start": 1, "end": 2, "score": 90}, {"start": 5, "end": 7, "score": 75}], "chosen": 0}]}})
    r = c.put("/api/ep/2/1/recording/take", json={"scene": sc["id"], "block": 0, "take": 1}).json()
    assert r["in"] == 4.85 and r["chosen"] == 1 and r["uncertain"] is True
    from glorfindel.rough_cut import build_package, load_template
    pkg = build_package(ep.scenes(), slug="S", template=load_template(None), th=ep.settings.thresholds, free_blocks=[{"titel": "Werbung", "after": None, "dauer": 81}])
    fb = next(cl for tr in pkg["tracks"].values() for cl in tr if cl["type"] == "free_block")
    assert abs((fb["end"] - fb["start"]) - 81) < 0.01


def test_word_marker_has_readable_name_and_roundtrips(tmp_path):
    from glorfindel.models import Scene, CommentBlock, AssetRef
    from glorfindel import script_docx
    sc = Scene(id="sz_01", titel="T", kommentar=[CommentBlock(text="Eins zwei drei vier", anker=[AssetRef(asset="art_0001", von=1, bis=3)])])
    f = tmp_path / "s.docx"
    script_docx.export_docx([sc], f, labels={"art_0001": "Alan Lee – Celebrimbor"})
    txt = "\n".join(p.text for p in __import__("docx").Document(str(f)).paragraphs)
    assert "art_0001~Alan_Lee" in txt
    res = script_docx.import_docx(f)
    ref = res.scenes["sz_01"]["kommentar"][0].anker[0]
    assert ref.asset == "art_0001" and ref.von == 1 and ref.bis == 3


def test_asset_delete_guard_and_artists(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    from glorfindel import pipeline
    ep = c.app.state.gl.episode(2, 1)
    pipeline.save_asset(ep, {"path": "x.png", "credit": "a"})
    sc = _scene(c, kommentar=[{"sprecher": "philipp", "text": "t", "anker": [{"asset": "art_0001"}]}])
    r = c.delete("/api/ep/2/1/assets/art_0001")
    assert r.status_code == 409 and "A" in r.json()["detail"]
    full = c.get("/api/ep/2/1/scenes").json()[0]
    full["kommentar"][0]["anker"] = []
    for k in ("report", "lock", "problems", "ausgabe"):
        full.pop(k, None)
    c.put(f"/api/ep/2/1/scenes/{sc['id']}", json=full)
    assert c.delete("/api/ep/2/1/assets/art_0001").status_code == 200
    assert c.put("/api/artists", json={"Ted Nasmith": "ted nasmith"}).status_code == 200
    assert c.get("/api/artists").json() == {"ted nasmith": "ted nasmith"}


def test_board_save_validation_and_map_sheet(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    ok = c.put("/api/ep/2/1/board", json={"scenes": [{"start": 1, "end": 20, "strang": "eregion"}]})
    assert ok.status_code == 200 and c.get("/api/ep/2/1/board").json()["scenes"][0]["strang"] == "eregion"
    assert c.put("/api/ep/2/1/board", json={"scenes": [{"start": 5, "end": 2}]}).status_code == 400
    # Karte mit Elementen rendern -> Blatt abrufbar
    from PIL import Image
    root = tmp_path / "od"
    Image.new("RGB", (400, 300), (30, 80, 50)).save(root / "karte.png")
    m = {"id": "map_01", "titel": "Test", "bild": "karte.png", "dauer": 4, "hinweise": "Fahrt nach Osten",
         "elemente": [{"typ": "marker", "x": .3, "y": .4, "text": "Eregion", "t0": 0}, {"typ": "pfeil", "punkte": [[.3, .4], [.7, .5]], "t0": 1}],
         "kamera": [{"t": 0, "rect": [0, 0, 1, 1]}, {"t": 3, "rect": [.2, .2, .5, .5]}]}
    assert c.put("/api/ep/2/1/maps/map_01", json=m).status_code == 200
    assert c.get("/api/ep/2/1/maps/map_01/sheet").status_code == 404
    jid = c.post("/api/ep/2/1/maps/map_01/render").json()["job"]
    import time
    for _ in range(100):
        j = c.get(f"/api/jobs/{jid}").json()
        if j["status"] != "laeuft":
            break
        time.sleep(0.1)
    assert j["status"] == "fertig", j.get("error")
    assert c.get("/api/ep/2/1/maps/map_01/sheet").status_code == 200
    assert c.delete("/api/ep/2/1/maps/map_01").status_code == 200


def test_update_check_never_fails(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("offline")))
    r = c.get("/api/update").json()
    assert r["newer"] is False and r["current"]
    from glorfindel.routes_core import _ver_tuple
    assert _ver_tuple("v0.2.0") > _ver_tuple("0.1.9")
    s = c.get("/api/system").json()
    assert "whisper" in s
