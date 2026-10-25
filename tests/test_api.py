import io
import time

import pytest
from fastapi.testclient import TestClient
from docx import Document

from glorfindel.api import create_app
from glorfindel.config import Settings
from glorfindel.deps import AppState

from conftest import make_clip, needs_ffmpeg


@pytest.fixture
def client(tmp_path):
    root = tmp_path / "OneDrive"
    root.mkdir()
    state = AppState(Settings(onedrive_root=str(root), user="danny"), persist=False)
    c = TestClient(create_app(state), base_url="http://localhost")
    c.root = root
    return c


def wait_job(c, jid, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        j = c.get(f"/api/jobs/{jid}").json()
        if j["status"] != "laeuft":
            return j
        time.sleep(0.2)
    raise TimeoutError(jid)


def test_routes_registered_and_health(client):
    assert client.get("/api/health").json()["ok"]
    paths = set(client.get("/api/openapi.json").json()["paths"])
    assert "/api/ep/{season}/{episode}/scenes" in paths and "/api/images/search" in paths
    assert len(paths) > 60


def test_security_rejects_foreign_host_and_origin(client):
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 403
    r = client.put("/api/settings", json=Settings().model_dump(), headers={"origin": "http://evil.example"})
    assert r.status_code == 403
    assert client.put("/api/settings", json=Settings().model_dump(), headers={"origin": "http://localhost:8765"}).status_code == 200


def test_settings_roundtrip_and_missing_root(client):
    s = client.get("/api/settings").json()
    assert s["_onedrive_ok"] and s["thresholds"]["max_segment_s"] == 9.5
    s["user"] = "maurice"
    client.put("/api/settings", json=s)
    assert client.get("/api/settings").json()["user"] == "maurice"
    empty = TestClient(create_app(AppState(Settings(), persist=False)), base_url="http://localhost")
    assert empty.get("/api/ep/3/1").status_code == 409


def test_fs_browser(client):
    (client.root / "A").mkdir()
    (client.root / "x.mp4").write_text("1")
    r = client.get("/api/fs", params={"path": str(client.root), "files": True}).json()
    assert [e["name"] for e in r["entries"]] == ["A", "x.mp4"]
    assert client.get("/api/fs", params={"path": str(client.root / "nix")}).status_code == 404


def test_episode_and_scene_crud_with_lock_and_report(client):
    assert client.post("/api/episodes", json={"season": 3, "episode": 1, "title": "Test"}).status_code == 200
    assert client.get("/api/episodes").json() == [{"season": 3, "episode": 1, "title": "Test"}]
    sc = client.post("/api/ep/3/1/scenes", json={"titel": "Schmiede", "strang": "eregion",
                     "segmente": [{"in": 10, "out": 21}]}).json()
    sid = sc["id"]
    lst = client.get("/api/ep/3/1/scenes").json()
    assert lst[0]["report"]["light"] == "rot" and lst[0]["problems"] == []
    sc["kommentar"] = [{"sprecher": "danny", "text": "- Eins\n- Zwei", "anker": []}]
    r = client.put(f"/api/ep/3/1/scenes/{sid}", json=sc).json()
    assert r["scene"]["kommentar"][0]["modus"] == "stichpunkte"
    assert client.put(f"/api/ep/3/1/scenes/{sid}", json={**sc, "id": "sz_99"}).status_code == 400
    assert client.post(f"/api/ep/3/1/scenes/{sid}/lock").json()["held"]
    ov = client.get("/api/ep/3/1").json()
    assert ov["report"]["series_s"] == 11 and len(ov["strands"]) == 4
    assert client.get("/api/ep/3/1/log").json()[0]["wer"] == "danny"
    assert client.get("/api/ep/3/1/version").json()["version"] > 0
    assert client.delete(f"/api/ep/3/1/scenes/{sid}").status_code == 200
    assert client.get("/api/ep/3/1/scenes").json() == []
    assert client.get("/api/ep/9/9").status_code == 404


def test_conflict_listing_and_resolution(client):
    client.post("/api/episodes", json={"season": 3, "episode": 1})
    sid = client.post("/api/ep/3/1/scenes", json={"titel": "A"}).json()["id"]
    d = client.root / "Mythen-Archiv/Videos/S3 E1/glorfindel/szenen"
    (d / f"{sid}-LAPTOP.json").write_text('{"id": "%s", "titel": "Andere Version"}' % sid, encoding="utf-8")
    cf = client.get("/api/ep/3/1/conflicts").json()
    assert len(cf) == 1 and cf[0]["b"]["titel"] == "Andere Version"
    assert [s["id"] for s in client.get("/api/ep/3/1/scenes").json()] == [sid]    # Kopie wird nicht als Szene geladen
    r = client.post("/api/ep/3/1/conflicts/resolve", json={"original": cf[0]["original"], "other": cf[0]["copy"], "keep": "copy"})
    assert r.status_code == 200 and client.get("/api/ep/3/1/scenes").json()[0]["titel"] == "Andere Version"
    bad = client.post("/api/ep/3/1/conflicts/resolve", json={"original": "C:/x.json", "other": "C:/y.json", "keep": "copy"})
    assert bad.status_code == 400


def test_word_export_import_and_legacy(client):
    client.post("/api/episodes", json={"season": 3, "episode": 1, "title": "T"})
    sid = client.post("/api/ep/3/1/scenes", json={"titel": "A", "kommentar": [{"sprecher": "philipp", "text": "Hallo Welt"}]}).json()["id"]
    r = client.get("/api/ep/3/1/script.docx")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    d = Document(io.BytesIO(r.content))
    for p in d.paragraphs:
        for run in p.runs:
            run.text = run.text.replace("Hallo", "Servus")
    buf = io.BytesIO()
    d.save(buf)
    files = {"file": ("s.docx", buf.getvalue(), "application/octet-stream")}
    assert client.post("/api/ep/3/1/script/import-preview", files=files).json()["changed"] == [sid]
    assert client.post("/api/ep/3/1/script/import", files={"file": ("s.docx", buf.getvalue())}).json()["changed"] == [sid]
    assert client.get("/api/ep/3/1/scenes").json()[0]["kommentar"][0]["text"] == "Servus Welt"
    leg = Document()
    for t in ["[Intro]", "Werbung", "[Szene Eins]", "P: Text eins", "[Szene Zwei]", "D: Text zwei"]:
        leg.add_paragraph(t)
    b2 = io.BytesIO()
    leg.save(b2)
    st = client.post("/api/ep/3/1/script/import-legacy", files={"file": ("l.docx", b2.getvalue())}).json()
    assert st["scenes"] == 2 and st["free_blocks"] == 1
    assert len(client.get("/api/ep/3/1/scenes").json()) == 3


@needs_ffmpeg
def test_sources_proxy_anchors_frames_and_compare(client):
    client.post("/api/episodes", json={"season": 3, "episode": 1})
    ref = make_clip(client.root / "Filme" / "ref.mp4", seconds=12, fps=24)
    hq = make_clip(client.root / "Filme" / "hq.mp4", seconds=12, fps=24)
    j = wait_job(client, client.post("/api/ep/3/1/sources", json={"path": "Filme/ref.mp4"}).json()["job"])
    assert j["status"] == "fertig" and j["result"]["role"] == "referenz" and j["result"]["path"] == "Filme/ref.mp4"
    j = wait_job(client, client.post("/api/ep/3/1/sources", json={"path": "Filme/hq.mp4", "role": "hq"}).json()["job"])
    assert j["result"]["id"] == "q2" and j["result"]["role"] == "hq"
    for sid in ("q1", "q2"):
        assert wait_job(client, client.post(f"/api/ep/3/1/sources/{sid}/proxy").json()["job"])["status"] == "fertig"
    assert client.get("/api/ep/3/1/sources/q1/proxy-status").json()["ready"]
    assert client.get("/api/ep/3/1/media/q1").status_code == 200
    a = client.put("/api/ep/3/1/sources/q2/anchors", json={"anchors": [{"ref": 2.0, "src": 2.0}]}).json()
    assert a["anchors"] == [{"ref": 2.0, "src": 2.0}]
    assert client.get("/api/ep/3/1/frame", params={"source": "q2", "t": 3.0}).status_code == 200
    cmp = client.get("/api/ep/3/1/compare", params={"a": "q1", "b": "q2", "t": 5.0}).json()
    assert cmp["correlation"] > 0.95 and cmp["diff"].startswith("/api/ep/3/1/compare-img/")
    assert client.get(cmp["diff"]).status_code == 200
    sc = client.post("/api/ep/3/1/scenes", json={"titel": "S", "segmente": [{"in": 3, "out": 8}]}).json()
    chk = client.get("/api/ep/3/1/scene-check", params={"source": "q2"}).json()
    assert chk[0]["scene"] == sc["id"] and not chk[0]["uncertain"]
    # Conform per API
    j = wait_job(client, client.post("/api/ep/3/1/conform", json={"source": "q2", "codec": "h264"}).json()["job"], 180)
    assert j["status"] == "fertig", j
    from pathlib import Path
    assert Path(j["result"]["file"]).exists() and (client.root / "Mythen-Archiv/Videos/S3 E1/Videoelemente_HQ/1.png").exists()
    # Rohschnitt per API
    j = wait_job(client, client.post("/api/ep/3/1/rough-cut", json={"with_stills": True}).json()["job"], 120)
    assert j["status"] == "fertig" and j["result"]["version"] == 1
    assert client.get("/api/ep/3/1/rough-cut").json()[0]["xml"]
    assert client.get("/api/ep/3/1/rough-cut/1/json").status_code == 200
    # Strang-Board
    j = wait_job(client, client.post("/api/ep/3/1/board/detect", json={"min_scene_s": 3}).json()["job"], 120)
    assert j["status"] == "fertig" and j["result"]["scenes"]
    assert client.get("/api/ep/3/1/board").json()["scenes"][0]["thumb"]


def test_images_assets_and_maps_api(client, tmp_path):
    from PIL import Image
    client.post("/api/episodes", json={"season": 3, "episode": 1})
    d = client.root / "Videomaterial" / "Bilder"
    d.mkdir(parents=True)
    Image.new("RGB", (80, 60), (30, 90, 200)).save(d / "alan lee - ringe 1.jpg")
    k = client.root / "Videomaterial" / "Karten"
    k.mkdir(parents=True)
    Image.new("RGB", (400, 300), (120, 150, 90)).save(k / "Eriador.png")
    assert wait_job(client, client.post("/api/images/index").json()["job"])["result"]["added"] == 1
    hits = client.get("/api/images/search", params={"q": "ringe"}).json()
    assert hits[0]["path"] == "Videomaterial/Bilder/alan lee - ringe 1.jpg"
    assert client.get("/api/images/thumb", params={"path": hits[0]["path"]}).status_code == 200
    assert client.get("/api/images/thumb", params={"path": "../../../etc/passwd"}).status_code in (400, 404)
    a = client.post("/api/ep/3/1/assets", json={"path": hits[0]["path"]}).json()
    assert a["id"] == "art_0001" and a["credit"] == "alan lee" and a["contour_color"].startswith("#")
    a["credit"] = "alan lee (ar)"
    assert client.put("/api/ep/3/1/assets/art_0001", json=a).json()["credit"] == "alan lee (ar)"
    assert client.post("/api/ep/3/1/assets", json={"url": "http://127.0.0.1/x.png"}).status_code == 400  # SSRF-Schutz
    assert client.get("/api/maps", params={"q": "eri"}).json()[0]["name"] == "Eriador.png"
    m = {"bild": "Videomaterial/Karten/Eriador.png", "dauer": 1.0, "elemente": [{"typ": "marker", "x": .5, "y": .5, "text": "Hier"}]}
    client.put("/api/ep/3/1/maps/k_eriador", json=m)
    j = wait_job(client, client.post("/api/ep/3/1/maps/k_eriador/render").json()["job"], 120)
    assert j["status"] == "fertig", j
    assert client.get("/api/ep/3/1/maps").json()[0]["placeholder_clip"].endswith("k_eriador_platzhalter.mp4")


def test_recording_api_without_whisper(client, tmp_path):
    client.post("/api/episodes", json={"season": 3, "episode": 1})
    client.post("/api/ep/3/1/scenes", json={"titel": "S", "kommentar": [{"sprecher": "danny", "text": "Hallo Welt Test"}]})
    assert client.post("/api/ep/3/1/recording", json={"path": "x.wav", "speaker": "nobody"}).status_code == 400
    if make_clip.__module__:
        f = make_clip(client.root / "Aufnahmen" / "d.mp4", seconds=5)
    rec = client.post("/api/ep/3/1/recording", json={"path": "Aufnahmen/d.mp4", "speaker": "danny"}).json()
    assert rec["id"] == "r_danny_1"
    assert client.get(f"/api/ep/3/1/recording/{rec['id']}/waveform").json()["peaks"]
    t = client.put("/api/ep/3/1/recording/block", json={"scene": "sz_01", "block": 0, "t_in": 1.0, "t_out": 4.0}).json()
    assert t["manual"] and client.get("/api/ep/3/1/recording").json()["scenes"]["sz_01"][0]["in"] == 1.0
    assert client.post("/api/ep/3/1/recording/adopt", json={"scene": "sz_01", "block": 0}).status_code == 400


def test_security_hardening_paths_and_csrf(client):
    client.post("/api/episodes", json={"season": 3, "episode": 1})
    sid = client.post("/api/ep/3/1/scenes", json={"titel": "A"}).json()["id"]
    d = client.root / "Mythen-Archiv/Videos/S3 E1/glorfindel/szenen"
    victim = client.root / "geheim.json"
    victim.write_text("{}", encoding="utf-8")
    sneaky = str(d / ".." / ".." / ".." / ".." / "geheim.json")        # lexikalisch "unter" szenen, real außerhalb
    r = client.post("/api/ep/3/1/conflicts/resolve", json={"original": str(d / f"{sid}.json"), "other": sneaky, "keep": "copy"})
    assert r.status_code == 400 and victim.exists()
    # Aufnahmen: nur Mediendateien
    (client.root / "notiz.txt").write_text("x")
    assert client.post("/api/ep/3/1/recording", json={"path": "notiz.txt", "speaker": "danny"}).status_code == 400
    # Browser-CSRF ohne Origin, aber als cross-site gekennzeichnet
    bad = client.put("/api/settings", json=Settings().model_dump(), headers={"sec-fetch-site": "cross-site"})
    assert bad.status_code == 403


@needs_ffmpeg
def test_frame_capture_makes_a_map_from_the_video(client):
    from PIL import Image
    client.post("/api/episodes", json={"season": 3, "episode": 1})
    make_clip(client.root / "Filme" / "ref.mp4", seconds=6, size="640x360")
    assert wait_job(client, client.post("/api/ep/3/1/sources", json={"path": "Filme/ref.mp4"}).json()["job"])["status"] == "fertig"
    r = client.post("/api/ep/3/1/frame", json={"source": "q1", "t": 2.5, "title": "Gasthof"})
    assert r.status_code == 200, r.text
    d = r.json()
    img = client.root / d["path"]
    assert img.exists() and Image.open(img).size == (640, 360)                  # volle Auflösung, nicht der Proxy
    assert d["map"]["titel"] == "Gasthof" and d["map"]["bild"] == d["path"] and d["map"]["id"] == "map_01"
    assert client.get("/api/maps/thumb", params={"path": d["path"]}).status_code == 200      # im Karteneditor ladbar
    assert client.get("/api/ep/3/1/maps").json()[0]["id"] == "map_01"
    again = client.post("/api/ep/3/1/frame", json={"source": "q1", "t": 3.0}).json()
    assert again["map"]["id"] == "map_02"
    assert client.post("/api/ep/3/1/frame", json={"source": "zzz", "t": 1}).status_code == 404


def test_group_shots_into_scenes(client):
    client.post("/api/episodes", json={"season": 3, "episode": 1})
    ids = [client.post("/api/ep/3/1/scenes", json={"titel": f"Shot {i}"}).json()["id"] for i in range(1, 4)]
    r = client.post("/api/ep/3/1/scenes-group", json={"ids": ids[:2], "titel": "Ankunft"}).json()
    assert r["gruppe"]["titel"] == "Ankunft" and r["gruppe"]["id"] == "g_01"
    scs = {s["id"]: s for s in client.get("/api/ep/3/1/scenes").json()}
    assert scs[ids[0]]["gruppe"] == scs[ids[1]]["gruppe"] == "g_01" and scs[ids[2]]["gruppe"] == ""
    # vorhandene Gruppe erweitern, umbenennen
    client.post("/api/ep/3/1/scenes-group", json={"ids": [ids[2]], "gruppe": "g_01"})
    assert client.put("/api/ep/3/1/groups/g_01", json={"titel": "Ankunft in Lindon"}).json()["titel"] == "Ankunft in Lindon"
    assert {s["gruppe"] for s in client.get("/api/ep/3/1/scenes").json()} == {"g_01"}
    # auflösen
    assert client.delete("/api/ep/3/1/groups/g_01").status_code == 200
    assert {s["gruppe"] for s in client.get("/api/ep/3/1/scenes").json()} == {""} and client.get("/api/ep/3/1/groups").json() == []
    assert client.post("/api/ep/3/1/scenes-group", json={"ids": ["sz_99"]}).status_code == 404
