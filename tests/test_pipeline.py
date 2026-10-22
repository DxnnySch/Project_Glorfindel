import json

import pytest
from PIL import Image

from glorfindel import pipeline
from glorfindel.models import AssetRef, CommentBlock, Segment, Strand
from glorfindel.service import Episode

from conftest import make_clip, needs_ffmpeg
from test_align_bullets import speak


@pytest.fixture
def ep(episode_root, tmp_path):
    root = tmp_path / "OneDrive"
    e = Episode.create(episode_root, 3, 1, "Test")
    ref = make_clip(root / "Filme" / "S3E1.mp4", seconds=60, fps=24, size="320x136")
    e.import_source(ref)
    return e


def seg(a, b):
    return Segment(**{"in": a, "out": b})


@needs_ffmpeg
def test_full_flow(ep, tmp_path):
    root = ep.p.root
    # Szenen: eine Textszene (mit Bildanker), eine Stichpunkt-Szene, andere Strang-Reihenfolge
    s1 = ep.create_scene(strang="numenor", titel="Hafen", segmente=[seg(5, 11), seg(20, 25)])
    s1.kommentar = [CommentBlock(sprecher="philipp", text="Celebrimbor schmiedet in Eregion die ersten Ringe der Macht",
                                 anker=[AssetRef(asset="art_0001", von=2, bis=6)])]
    ep.save_scene(s1)
    s2 = ep.create_scene(strang="eregion", titel="Schmiede", segmente=[seg(30, 38)])
    s2.kommentar = [CommentBlock(sprecher="philipp", modus="stichpunkte",
                                 stichpunkte=["Khazad-dûm Durin Mithril", "Sauron Annatar Geschenke"],
                                 anker=[AssetRef(asset="art_0002", von=1, bis=None, einheit="stichpunkt")])]
    ep.save_scene(s2)
    ep.save_strands([Strand(id="eregion", name="Eregion", order=0), Strand(id="numenor", name="Númenor", order=1)])
    assert [s.id for s in pipeline.ordered_scenes(ep)] == [s2.id, s1.id]

    # Assets
    (root / "Bilder").mkdir()
    Image.new("RGB", (100, 100), (10, 50, 200)).save(root / "Bilder" / "alan lee - hafen 1.jpg")
    pipeline.save_asset(ep, {"id": "art_0001", "path": "Bilder/alan lee - hafen 1.jpg", "credit": "alan lee",
                             "contour_color": "#0a32c8"})
    pipeline.save_asset(ep, {"id": "art_0002", "path": "Bilder/john howe.jpg"})

    # Aufnahme (Fake-Transkript statt Whisper)
    rec_file = make_clip(root / "Aufnahmen" / "philipp.mp4", seconds=40)
    rec = pipeline.add_recording(ep, str(rec_file), "philipp")
    tr = []
    tr += speak("Bei den Schmieden Khazad-dûm sehen wir Durin und den Mithril", 3)
    tr += speak("dann kommt Sauron als Annatar und bringt Geschenke", 10)
    tr += speak("Celebrimbor schmiedet in Eregion die ersten Ringe der Macht", 20)
    data = pipeline.run_alignment(ep, transcripts={rec["id"]: tr})
    assert not data["scenes"][s1.id][0].get("missing") and not data["scenes"][s2.id][0].get("missing")
    assert ep.scene(s1.id).status == "abgeglichen"
    assert data["scenes"][s2.id][0]["stichpunkte"][1]["in"] >= 9.9

    # Handkorrektur bleibt beim erneuten Abgleich erhalten
    pipeline.set_block_timing(ep, s1.id, 0, 19.0, 31.0)
    data = pipeline.run_alignment(ep, transcripts={rec["id"]: tr})
    assert data["scenes"][s1.id][0]["in"] == 19.0 and data["scenes"][s1.id][0]["manual"]

    # Gesprochenen Text übernehmen
    sc2 = pipeline.adopt_spoken_text(ep, s2.id, 0)
    assert sc2.kommentar[0].modus == "text" and "Annatar" in sc2.kommentar[0].text
    assert sc2.kommentar[0].anker[0].einheit == "wort"

    # Rohschnitt
    res = pipeline.build_rough_cut(ep, ep.p.root / "none")
    assert res["version"] == 1 and (ep.p.stills / "1.png").exists() and (ep.p.stills / "2.png").exists()
    pkg = json.loads(open(res["json"], encoding="utf-8").read())
    v1 = sorted(pkg["tracks"]["V1"], key=lambda c: c["start"])
    assert [c["type"] for c in v1] == ["scene_segment", "still", "scene_segment", "scene_segment", "still"]
    assert v1[0]["scene"] == s2.id                                      # Strang-Reihenfolge
    arts = [c for tk in ("V3", "V4") for c in pkg["tracks"].get(tk, []) if c["type"] == "artwork"]
    assert {a["ref"] for a in arts} == {"art_0001", "art_0002"}
    assert any(c["text"] == "© alan lee" for c in pkg["tracks"]["V10"])
    assert any(c.get("rec") == rec["id"] and not c.get("placeholder") for c in pkg["tracks"]["A2"])
    assert (ep.p.gl / "schnitt" / "schnitt_v1.xml").exists()
    res2 = pipeline.build_rough_cut(ep, ep.p.root / "none", with_stills=False)
    assert res2["version"] == 2 and (ep.p.gl / "schnitt" / "schnitt_v1.json").exists()   # nichts überschrieben
    # Standbild hat die Zielgröße
    assert Image.open(ep.p.stills / "1.png").size == (1920, 800)


@needs_ffmpeg
def test_still_times_modes(ep):
    from glorfindel.models import Scene
    sc = [Scene(id="a", segmente=[seg(1, 2), seg(5, 6)]), Scene(id="b", segmente=[seg(9, 10)], standbild="start"),
          Scene(id="c", segmente=[seg(20, 30)], standbild="aus")]
    assert pipeline.still_times(sc) == {"1.png": 6, "2.png": 9}
