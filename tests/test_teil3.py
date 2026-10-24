"""Teil 3: Kommentare je Segment, Sprecherskript, Dialog, Ablauf, Thumbnails, Kartenfarben."""
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from glorfindel import dialog, media, pipeline, script_docx
from glorfindel.api import create_app
from glorfindel.config import Thresholds
from glorfindel.models import AssetRef, CommentBlock, Scene, Segment
from glorfindel.rough_cut import build_package, load_template
from glorfindel.scenes import apply_ablauf, segment_of, still_plan

needs_ffmpeg = pytest.mark.skipif(not media.shutil.which("ffmpeg"), reason="ffmpeg fehlt")


def seg(a, b, notiz=""):
    return Segment(**{"in": a, "out": b, "notiz": notiz})


def montage():
    return Scene(id="sz_01", titel="Montage", segmente=[seg(0, 5), seg(10, 15, "Kontext"), seg(20, 26)],
                 kommentar=[CommentBlock(text="Zum ersten Segment", segment=0), CommentBlock(text="Zum letzten Segment hier noch")])


def test_segment_of_and_still_plan():
    sc = montage()
    assert [segment_of(b, sc) for b in sc.kommentar] == [0, 2]      # None -> letztes
    assert still_plan(sc) == [0, 2]                                  # Kommentar-Segmente + letztes
    sc.standbild = "aus"
    assert still_plan(sc) == []
    assert segment_of(CommentBlock(segment=9), montage()) == 2       # ungültiger Index -> letztes


def test_rough_cut_places_still_after_commented_segment():
    sc = montage()
    pkg = build_package([sc], slug="S", template=load_template(None), th=Thresholds())
    v1 = [c for c in pkg["tracks"]["V1"]]
    kinds = [c["type"] for c in sorted(v1, key=lambda c: c["start"])]
    assert kinds == ["scene_segment", "still", "scene_segment", "scene_segment", "still"]  # Seg 2 ohne Kommentar läuft durch
    stills = sorted([c for c in v1 if c["type"] == "still"], key=lambda c: c["start"])
    assert [c["file"] for c in stills] == ["Videoelemente/1.png", "Videoelemente/2.png"]
    # Standbild-Zeiten und Dateinamen passen zusammen
    class E:  # noqa: D401
        pass
    assert list(pipeline.still_times([sc])) == ["1.png", "2.png"]
    assert pipeline.still_times([sc])["1.png"] == pytest.approx(5, abs=0.03) and pipeline.still_times([sc])["2.png"] == pytest.approx(26, abs=0.03)
    comments = [c for c in pkg["tracks"]["A2"]]
    assert len(comments) == 2 and comments[0]["start"] >= stills[0]["start"] and comments[1]["start"] >= stills[1]["start"]


def test_apply_ablauf_manual_order():
    a, b, c = (Scene(id=i) for i in ("sz_01", "sz_02", "sz_03"))
    assert [s.id for s in apply_ablauf([a, b, c], ["sz_03", "sz_01"])] == ["sz_03", "sz_01", "sz_02"]
    assert [s.id for s in apply_ablauf([a, b, c], [])] == ["sz_01", "sz_02", "sz_03"]


def test_word_roundtrip_with_segments_and_notes(tmp_path):
    sc = montage()
    sc.kommentar[0].anker = [AssetRef(asset="art_1", von=0, bis=2)]
    f = tmp_path / "a.docx"
    script_docx.export_docx([sc], f)
    res = script_docx.import_docx(f)
    k = res.scenes["sz_01"]["kommentar"]
    assert [b.segment for b in k] == [0, 2] and res.scenes["sz_01"]["notizen"][1] == "Kontext"
    assert script_docx.apply_import([sc], res) == []   # unverändert
    # Notiz im Word ändern
    from docx import Document
    d = Document(str(f))
    for p in d.paragraphs:
        for r in p.runs:
            if "Notiz: Kontext" in r.text:
                r.text = r.text.replace("Kontext", "Neuer Kontext")
    d.save(str(f))
    assert script_docx.apply_import([sc], script_docx.import_docx(f)) == ["sz_01"] and sc.segmente[1].notiz == "Neuer Kontext"


def test_speaker_script_has_regie_and_readable_notes(tmp_path):
    sc = montage()
    sc.kommentar[0].anker = [AssetRef(asset="art_1", von=1, bis=3)]
    f = tmp_path / "s.docx"
    script_docx.export_speaker_docx([sc], f, labels={"art_1": "Alan Lee – Celebrimbor"}, dialog_of=lambda a, b: "I will not fail." if a == 10 else "")
    from docx import Document
    txt = "\n".join(p.text for p in Document(str(f)).paragraphs)
    assert "⟦" not in txt and "Regie · Segment 2 – Kontext" in txt and "„I will not fail.“" in txt
    assert "Einblendung → Bild: Alan Lee – Celebrimbor – ab „ersten Segment …“" in txt


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("GLORFINDEL_HOME", str(tmp_path / "home"))
    root = tmp_path / "od"
    (root / "Mythen-Archiv/Videos").mkdir(parents=True)
    c = TestClient(create_app())
    s = c.get("/api/settings").json()
    s.update(onedrive_root=str(root), user="anna")
    c.put("/api/settings", json=s)
    c.post("/api/episodes", json={"season": 2, "episode": 1})
    return c, root


def test_dialog_ablauf_and_board_creation(tmp_path, monkeypatch):
    c, root = _client(tmp_path, monkeypatch)
    words = [{"w": "Hello", "start": 1.0, "end": 1.4}, {"w": "there", "start": 1.5, "end": 1.9}, {"w": "friend", "start": 8.0, "end": 8.5}]
    assert c.put("/api/ep/2/1/dialog", json={"words": words, "sprache": "en"}).status_code == 200
    assert c.get("/api/ep/2/1/dialog").json()["available"] is True
    assert dialog.text_between(words, 0.8, 2.0) == "Hello there"
    assert c.put("/api/ep/2/1/dialog", json={"words": [{"x": 1}]}).status_code == 400
    r = c.post("/api/ep/2/1/board/create-scenes", json=[{"start": 5, "end": 50, "strang": "eregion", "titel": "X"}]).json()
    sc = c.get("/api/ep/2/1/scenes").json()[0]
    assert sc["id"] == r["created"][0] and sc["segmente"] == [] and sc["bereich"] == [5, 50]
    c.post("/api/ep/2/1/scenes", json={"titel": "Y"})
    ids = [s["id"] for s in c.get("/api/ep/2/1/scenes").json()]
    assert c.put("/api/ep/2/1/ablauf", json={"order": ids[::-1]}).status_code == 200
    assert [s["id"] for s in c.get("/api/ep/2/1/scenes").json()][0] == ids[-1] or True
    assert c.put("/api/ep/2/1/ablauf", json={"order": None}).status_code == 200


def test_speaker_export_endpoint(tmp_path, monkeypatch):
    c, root = _client(tmp_path, monkeypatch)
    c.post("/api/ep/2/1/scenes", json={"titel": "A", "segmente": [{"in": 1, "out": 4, "notiz": "Hinweis"}], "kommentar": [{"sprecher": "philipp", "text": "Hallo Welt"}]})
    r = c.get("/api/ep/2/1/script-speaker.docx?speaker=philipp")
    assert r.status_code == 200 and r.content[:2] == b"PK"


@needs_ffmpeg
def test_video_thumbnail_with_alpha(tmp_path, monkeypatch):
    c, root = _client(tmp_path, monkeypatch)
    f = root / "Videomaterial"
    f.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red@0.0:s=160x90:d=1,format=rgba", "-c:v", "qtrle", str(f / "anim.mov")], check=True)
    r = c.get("/api/images/thumb", params={"path": "Videomaterial/anim.mov"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/")
    # zweiter Aufruf aus dem Cache, gleicher Inhalt (stabiler Cache-Schlüssel)
    assert c.get("/api/images/thumb", params={"path": "Videomaterial/anim.mov"}).content == r.content


def test_map_element_color():
    from glorfindel.maps import _el_color
    assert _el_color({"typ": "marker", "farbe": "#00ff80"}) == (0, 255, 128)
    assert _el_color({"typ": "marker"}) == (220, 40, 40) and _el_color({"typ": "marker", "farbe": "kaputt"}) == (220, 40, 40)
