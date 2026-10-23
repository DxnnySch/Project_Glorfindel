"""Bauplan für Premiere aus einem Schnittpaket."""
import json
from pathlib import Path

import pytest
from PIL import Image

from glorfindel.config import Thresholds
from glorfindel.models import AssetRef, CommentBlock, Scene, Segment
from glorfindel.premiere_plan import PlanEnv, build_plan, hex_to_argb16, load_recipes, track_index
from glorfindel.rough_cut import build_package, load_template

TH, TPL = Thresholds(), load_template()


def seg(a, b):
    return Segment(**{"in": a, "out": b})


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "OD"
    (root / "Bilder").mkdir(parents=True)
    Image.new("RGB", (2000, 1000), (10, 80, 200)).save(root / "Bilder" / "alan lee - hafen.jpg")
    Image.new("RGB", (800, 1200), (200, 80, 10)).save(root / "Bilder" / "john howe.jpg")
    calls = []

    def credit(text, art, x):
        calls.append((text, art, x))
        p = tmp_path / f"c{len(calls)}.png"
        p.write_bytes(b"png")
        return p

    e = PlanEnv(root=root, episode_media=tmp_path / "ref_cfr.mp4", stills_dir=root / "Videoelemente", credit=credit,
                image_size=lambda p: Image.open(p).size, recipes=load_recipes(), premiere={"project": "F:/Vorlage.prproj"},
                doppel=TPL["doppelbild"])
    e.calls = calls
    return e


def package(**kw):
    scenes = [Scene(id="sz_01", titel="Schmiede", segmente=[seg(100, 106), seg(120, 125)],
                    kommentar=[CommentBlock(sprecher="philipp", text=" ".join(["wort"] * 26),
                                            anker=[AssetRef(asset="a1", von=2, bis=12), AssetRef(asset="a2", von=8, bis=20)])]),
              Scene(id="sz_02", titel="Hafen", segmente=[seg(300, 304)], kommentar=[CommentBlock(sprecher="danny", text="kurz hier")])]
    assets = {"a1": {"path": "Bilder/alan lee - hafen.jpg", "credit": "alan lee", "contour_color": "#d45329"},
              "a2": {"path": "Bilder/john howe.jpg"}}
    pkg = build_package(scenes, slug="S3 E1", template=TPL, th=TH, assets=assets, **kw)
    for tr in pkg["tracks"].values():
        for c in tr:
            if c["type"] == "comment" and not c.get("placeholder"):
                c["rec_path"] = "Aufnahmen/philipp.wav"
    return pkg


def test_track_index_and_color():
    assert track_index("V10") == ("video", 9) and track_index("A4") == ("audio", 3)
    assert hex_to_argb16("#d45329") == [0xFF00, 0xD400, 0x5300, 0x2900]


def test_plan_structure_media_and_stills(env):
    plan = build_plan(package(), env)
    kinds = plan["stats"]["by_kind"]
    assert kinds["episode"] == 3 and kinds["still"] == 2 and kinds["anim"] >= 3 and kinds["artwork"] == 2
    assert kinds["blur"] >= 2 and kinds["credit"] >= 3                       # Artwork-Credits + © amazon studios je Szene
    eps = [c for c in plan["clips"] if c["kind"] == "episode"]
    assert eps[0]["src_in"] == 100 and eps[0]["src_out"] == 106 and eps[0]["audio"] == 3 and eps[0]["track"] == 0
    still = next(c for c in plan["clips"] if c["kind"] == "still")
    m = {x["id"]: x for x in plan["media"]}
    assert Path(m[still["media"]]["path"]).parent == env.stills_dir and m[eps[0]["media"]]["kind"] == "episode"
    assert plan["template"]["project"] == "F:/Vorlage.prproj" and plan["episode_sequence"] == "S3 E1 Sequenz"
    json.dumps(plan)                                                          # vollständig JSON-fähig


def test_artwork_uses_the_original_effect_chain_with_contour_and_square_crop(env):
    plan = build_plan(package(), env)
    a1, a2 = sorted([c for c in plan["clips"] if c["kind"] == "artwork"], key=lambda c: c["start"])
    assert [e["id"] for e in a1["effects"]] == ["drop_shadow", "zoom", "fancy_out", "fancy_in"]
    assert a1["crop"] == {"links": 25.0, "rechts": 25.0, "oben": 0.0, "unten": 0.0} and a1["scale"] == pytest.approx(100.0)
    assert a2["crop"]["oben"] == pytest.approx(16.667, abs=0.01) and a2["crop"]["links"] == 0 and a2["scale"] == pytest.approx(125.0)
    dur = a1["end"] - a1["start"]
    out = next(e for e in a1["effects"] if e["id"] == "fancy_out")
    rahmen = next(p for p in out["params"] if p["name"] == "Rahmen")
    assert rahmen["keyframes"][0][0] == pytest.approx(dur - 0.5333, abs=0.01)
    assert rahmen["keyframes"][-1][0] == pytest.approx(dur - 0.0167, abs=0.01)
    assert [v for _, v in rahmen["keyframes"]] == [0.0, 8.0, 500.0]
    fin = next(e for e in a1["effects"] if e["id"] == "fancy_in")
    assert next(p for p in fin["params"] if p["name"] == "Rahmen")["keyframes"] == [[0.0, 500.0], [0.5, 8.0]]
    for e in (out, fin):                                                      # Konturfarbe aus dem Asset
        assert next(p for p in e["params"] if p["name"] == "Konturfarbe")["value"] == {"argb16": [0xFF00, 0xD400, 0x5300, 0x2900]}
    zoom = next(e for e in a1["effects"] if e["id"] == "zoom")
    assert next(p for p in zoom["params"] if p["name"].startswith("Skalierungsh"))["keyframes"][-1] == [120.0, 240.0]
    assert all(t >= 0 for e in a1["effects"] for p in e["params"] for t, _ in p.get("keyframes", []))


def test_credits_blur_voice_and_markers(env):
    plan = build_plan(package(), env)
    texts = [(t, art) for t, art, _ in env.calls]
    assert ("© alan lee", "artwork") in texts and ("© amazon studios", "amazon") in texts and ("© john howe", "artwork") in texts
    cred = [c for c in plan["clips"] if c["kind"] == "credit" and c["name"] == "© alan lee"][0]
    art = [c for c in plan["clips"] if c["kind"] == "artwork"][0]
    assert cred["start"] == art["start"] and cred["end"] == art["end"] and cred["fade"] == pytest.approx(0.42) and cred["track"] == 9
    blur = sorted([c for c in plan["clips"] if c["kind"] == "blur"], key=lambda c: c["start"])
    assert blur[0]["effects"][0]["id"] == "gauss_in" and blur[0]["effects"][0]["params"][0]["keyframes"] == [[0.0, 0.0], [0.5, 15.0]]
    assert blur[1]["effects"][0]["id"] == "gauss_const" and blur[1]["effects"][0]["params"][0]["value"] == 15.0
    assert [c for c in plan["clips"] if c["kind"] == "voice"] == []           # alle Blöcke noch ohne Aufnahme -> Platzhalter
    assert any("noch keine Aufnahme" in w for w in plan["warnings"])
    assert plan["markers"] and plan["markers"][0]["time"] == 0


def test_voice_clips_with_alignment_and_pause_play_template(env):
    al = {"scenes": {"sz_01": [{"block": 0, "rec": "r1", "in": 10.0, "out": 18.0, "words": []}]}}
    plan = build_plan(package(alignment=al), env)
    v = [c for c in plan["clips"] if c["kind"] == "voice"]
    media = {m["id"]: m for m in plan["media"]}
    assert len(v) == 1 and v[0]["src_in"] == 10.0 and v[0]["track"] == 1 and Path(media[v[0]["media"]]["path"]).name == "philipp.wav"
    anims = [c for c in plan["clips"] if c["kind"] == "anim"]
    assert {a["template"] for a in anims} == {"Pause", "Play"} and all(a["track"] == 6 for a in anims)     # V7 wie im Original


def test_missing_artwork_is_skipped_with_warning(env):
    pkg = package()
    pkg["tracks"]["V3"][0]["file"] = "Bilder/gibt-es-nicht.jpg"
    plan = build_plan(pkg, env)
    assert sum(1 for c in plan["clips"] if c["kind"] == "artwork") == 1
    assert any("nicht gefunden" in w for w in plan["warnings"])


def test_double_layout_uses_template_positions_and_credit_x(env):
    scenes = [Scene(id="sz_01", segmente=[seg(0, 5)], kommentar=[CommentBlock(text=" ".join(["w"] * 30), anker=[
        AssetRef(asset="a1", von=0, bis=10, layout="doppel_links"), AssetRef(asset="a2", von=0, bis=10, layout="doppel_rechts")])])]
    assets = {"a1": {"path": "Bilder/alan lee - hafen.jpg", "credit": "a"}, "a2": {"path": "Bilder/john howe.jpg", "credit": "b"}}
    plan = build_plan(build_package(scenes, slug="S", template=TPL, th=TH, assets=assets), env)
    arts = {c["position"][0]: c for c in plan["clips"] if c["kind"] == "artwork"}
    assert set(arts) == {0.27, 0.73}
    xs = sorted(x for _, art, x in env.calls if art == "artwork")
    assert xs == [0.27, 0.73]
    assert {c["track"] for c in plan["clips"] if c["kind"] == "credit" and c["name"] in ("© a", "© b")} == {9, 12}
