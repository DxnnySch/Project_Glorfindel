import json

import pytest
from defusedxml import ElementTree as DET

from glorfindel.config import Thresholds
from glorfindel.fcpxml import to_fcpxml
from glorfindel.models import AssetRef, CommentBlock, Scene, Segment
from glorfindel.rough_cut import (build_package, credit_from_filename, credit_text, load_template,
                                  next_version, write_package)

TH = Thresholds()
TPL = load_template()


def seg(a, b):
    return Segment(**{"in": a, "out": b})


def two_scenes():
    return [
        Scene(id="sz_01", strang="eregion", titel="Schmiede", segmente=[seg(100, 106), seg(120, 125)],
              kommentar=[CommentBlock(sprecher="philipp", text=" ".join(["wort"] * 26),
                                      anker=[AssetRef(asset="a1", von=2, bis=12), AssetRef(asset="a2", von=8, bis=20)])]),
        Scene(id="sz_02", strang="numenor", titel="Hafen", segmente=[seg(300, 312)],  # 12 s -> rot
              kommentar=[CommentBlock(sprecher="danny", text="kurz und knapp hier")]),
    ]


ASSETS = {"a1": {"path": "Bilder/alan lee - 3.jpg", "credit": "alan lee", "contour_color": "#112233"},
          "a2": {"path": "Bilder/john howe.jpg"}}


def pkg(**kw):
    return build_package(two_scenes(), slug="S3 E1", template=TPL, th=TH, assets=ASSETS, **kw)


def test_basic_layout_and_order():
    p = pkg()
    v1 = sorted(p["tracks"]["V1"], key=lambda c: c["start"])
    kinds = [c["type"] for c in v1]
    assert kinds == ["scene_segment", "scene_segment", "still", "scene_segment", "still"]
    # lückenlos
    for a, b in zip(v1, v1[1:]):
        assert b["start"] == pytest.approx(a["end"], abs=1 / 60)
    assert p["duration"] == pytest.approx(v1[-1]["end"])
    assert p["sequence"]["name"].startswith("Rohschnitt S3 E1 v1")


def test_pause_and_play_offsets():
    p = pkg()
    anims = sorted([c for c in p["tracks"]["V2"] if c["type"] == "anim"], key=lambda c: c["start"])
    stills = sorted([c for c in p["tracks"]["V1"] if c["type"] == "still"], key=lambda c: c["start"])
    assert anims[0]["name"] == "Pause" and anims[0]["start"] == pytest.approx(stills[0]["start"] - 0.63, abs=1 / 60)
    assert anims[1]["name"] == "Play" and anims[1]["start"] == pytest.approx(stills[0]["end"] - 0.68, abs=1 / 60)
    assert anims[1]["end"] - anims[1]["start"] == pytest.approx(1.32, abs=1 / 60)
    assert len(anims) == 3  # Pause, Play, Pause der zweiten Szene; nach der letzten Szene kein Play


def test_artworks_alternate_tracks_credits_and_blur():
    p = pkg()
    arts = [c for tk in ("V3", "V4") for c in p["tracks"].get(tk, []) if c["type"] == "artwork"]
    assert len(arts) == 2
    a1, a2 = sorted(arts, key=lambda c: c["start"])
    overlap = a2["start"] < a1["end"]
    assert overlap and {t for t in ("V3", "V4") if any(c is a1 for c in p["tracks"][t])} != \
        {t for t in ("V3", "V4") if any(c is a2 for c in p["tracks"][t])}
    credits = sorted(p["tracks"]["V10"], key=lambda c: c["start"])
    assert [c["text"] for c in credits] == ["© alan lee", "© john howe"]
    assert credits[0]["start"] == a1["start"] and credits[0]["end"] == a1["end"]
    fancy = a1["effects"][0]
    assert fancy["recipe"] == "fancy_in" and fancy["contour"] == "#112233"
    blur = [c for c in p["tracks"]["V2"] if c["type"] == "blur"]
    assert blur[0]["effects"][0]["recipe"] == "gauss_in"
    assert blur[0]["end"] - blur[0]["start"] == pytest.approx(2.0, abs=1 / 60)
    assert any("John" not in w and "john howe" in w for w in p["warnings"])  # Credit aus Dateiname


def test_warnings_for_long_segment_and_missing_recording():
    p = pkg()
    assert any("sz_02" in w and "12.0 s" in w for w in p["warnings"])
    assert any("noch keine Aufnahme" in w for w in p["warnings"])


def test_alignment_drives_timing_and_audio_tracks():
    al = {"scenes": {"sz_02": [{"block": 0, "rec": "r_danny", "in": 50.0, "out": 56.0,
                                "words": [{"i": i, "start": 50 + i, "end": 51 + i} for i in range(4)]}]}}
    p = pkg(alignment=al)
    c = p["tracks"]["A3"][0]
    assert c["src_in"] == 50.0 and c["end"] - c["start"] == pytest.approx(6.0, abs=1 / 60) and "placeholder" not in c
    assert p["tracks"]["A2"][0]["placeholder"]  # Philipp noch ohne Aufnahme
    stills = sorted([c for c in p["tracks"]["V1"] if c["type"] == "still"], key=lambda c: c["start"])
    assert stills[1]["end"] - stills[1]["start"] >= 0.3 + 6.0


def test_free_blocks_and_map_markers():
    sc = two_scenes()
    sc[0].kommentar[0].anker.append(AssetRef(karte="k_moria", von=0, bis=3))
    p = build_package(sc, slug="S3 E1", template=TPL, th=TH, assets=ASSETS,
                      maps={"k_moria": {"hinweise": "Heerzug in Rot"}},
                      free_blocks=[{"after": "sz_01", "titel": "Werbung", "text": "viel text " * 30}])
    texts = [m["text"] for m in p["markers"]]
    assert any("Heerzug in Rot" in t for t in texts) and any("Freier Block: Werbung" in t for t in texts)
    gap = p["tracks"]["GAP"][0]
    assert gap["end"] - gap["start"] == pytest.approx(60 / TH.words_per_second, abs=0.1)
    assert any(c["type"] == "map_placeholder" for tk in ("V3", "V4") for c in p["tracks"][tk])


def test_still_extended_when_artwork_overhangs():
    sc = [Scene(id="x", segmente=[seg(0, 5)], standbild="ende",
                kommentar=[CommentBlock(text="a b c d", anker=[AssetRef(asset="a1", von=0, bis=None)])])]
    p = build_package(sc, slug="S", template=TPL, th=TH, assets=ASSETS)
    still = next(c for c in p["tracks"]["V1"] if c["type"] == "still")
    art_end = max(c["end"] for c in p["tracks"]["V3"] if c["type"] == "artwork")
    assert still["end"] >= art_end


def test_credit_helpers():
    assert credit_text("© {kuenstler}", "Alan Lee") == "© alan lee"
    assert credit_from_filename("Bilder/Alan Lee - Ringe 12.jpg") == "alan lee"
    assert credit_from_filename("john_howe_3.png") == "john howe"


def test_versioning_never_overwrites(tmp_path):
    p = pkg()
    f1 = write_package(p, tmp_path)
    assert next_version(tmp_path) == 2
    p["version"] = 2
    f2 = write_package(p, tmp_path)
    assert f1 != f2 and json.loads(f1.read_text(encoding="utf-8"))["version"] == 1


def test_fcpxml_is_wellformed_and_has_structure():
    p = pkg()
    xml = to_fcpxml(p, "Folgen/S02E07.mp4", 3000.0, "F:/OneDrive")
    root = DET.fromstring(xml.split("<!DOCTYPE xmeml>")[1])
    assert root.tag == "xmeml"
    assert root.find("sequence/name").text.startswith("Rohschnitt")
    assert len(root.findall("sequence/media/video/track")) == 3
    assert len(root.findall("sequence/marker")) == len(p["markers"])
    v1 = root.findall("sequence/media/video/track")[0].findall("clipitem")
    assert len(v1) == 5
    assert root.find(".//file/pathurl").text.startswith("file://localhost/")
