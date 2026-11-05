"""Fachliche Seite der Panel-Werkzeuge: Rezepte, Artwork-Bau, Credits, Ton-Blenden, Szene am Abspielkopf."""
import json
from pathlib import Path

import pytest
from PIL import Image

from glorfindel import premiere_tools as pt
from glorfindel.premiere_plan import load_recipes, with_library

ROOT = Path(__file__).resolve().parents[1]
LIB = json.loads((ROOT / "vorlagen" / "effekt_bibliothek.json").read_text(encoding="utf-8"))


@pytest.fixture
def ctx(tmp_path):
    img = tmp_path / "Alan Lee - Hafen 3.jpg"
    Image.new("RGB", (2000, 1000), (10, 80, 200)).save(img)
    masks = tmp_path / "masken"
    masks.mkdir()
    for n in ("Maske.png", "Maske Quadrat.png"):
        Image.new("RGBA", (1920, 800), (0, 0, 0, 255)).save(masks / n)
    tpl = tmp_path / "mogrt"
    tpl.mkdir()
    return pt.ToolContext(recipes=with_library(load_recipes(), LIB), settings={"art_px": 1000.0, "landscape_px": 1536.0, "mask": "auto",
                                                                            "artwork_effects": ["drop_shadow", "zoom", "fancy_out", "fancy_in"], "fps": 24.0},
                          masks=masks, nested_preset="C:/x/artwork.sqpreset", credit_mogrt={}, artist_db={"alan lee": "alan lee"},
                          cache=tmp_path / "cache", frame_box=None, plan=None, scenes={}), img


def test_config_groups_in_out_pairs_and_lists_credit_arts(ctx):
    c, _ = ctx
    cfg = pt.config(c)
    ids = {e["id"]: e for e in cfg["effekte"]}
    assert ids["karte"]["ein"] == "karte_in" and ids["karte"]["aus"] == "karte_out"
    assert ids["zoom_schnell"]["einzel"] == "zoom_schnell" and "ein" not in ids["zoom_schnell"]
    assert {a["art"] for a in cfg["credits"]} == {"amazon", "artwork", "musik"}
    assert "calibration" in cfg
    assert cfg["uebergang"]["match_name"] == "AE.ADBE Cross Dissolve New" and cfg["uebergang"]["dauer"] == pytest.approx(0.4167)


def test_effects_resolve_to_clip_time_for_each_clip(ctx):
    c, _ = ctx
    out = pt.effects(c, ["karte_in", "karte_out"], [{"dur": 6.0}, {"dur": 2.0}])
    assert len(out["clips"]) == 2 and [e["id"] for e in out["clips"][0]] == ["karte_in", "karte_out"]
    pos = lambda eff: next(p for p in eff["params"] if p.get("keyframes"))["keyframes"]
    k_in, k_out = pos(out["clips"][0][0]), pos(out["clips"][0][1])
    assert k_in[0][0] == pytest.approx(0.0, abs=1e-6) and max(t for t, _ in k_out) == pytest.approx(6.0, abs=0.5)    # „aus“ hängt am Clipende
    k_short = pos(out["clips"][1][1])
    assert max(t for t, _ in k_short) <= 2.0 + 1e-6
    with pytest.raises(ValueError, match="unbekannt"):
        pt.effects(c, ["gibt_es_nicht"], [{"dur": 1}])


def test_audio_fade_uses_equal_power_keyframes_with_defaults(ctx):
    c, _ = ctx
    k = pt.audiofade(c, 10.0, ein=1.0, aus=1.0)["keyframes"]
    assert k[0] == [0.0, 0.0] and k[-1][1] == pytest.approx(0.0) and max(g for _, g in k) == pytest.approx(1.0)
    assert pt.audiofade(c, 10.0, ein=0.0, aus=0.0)["keyframes"] == []
    assert pt.audiofade(c, 10.0)["keyframes"]                                               # Standarddauer aus den Rezepten


def test_artwork_spec_matches_build_rules(ctx):
    c, img = ctx
    r = pt.artwork(c, str(img), 7.0)
    n = r["nested"]
    assert n["image"] == str(img) and n["mask"].endswith("Maske.png") and n["dur"] == 7.0              # Querformat: breite Maske
    assert (n["image_track"], n["mask_track"], n["matte_track"]) == (2, 4, 5)
    assert n["image_scale"] > 0 and n["mask_scale"] > 0 and len(n["image_position"]) == 2
    assert n["preset"] == "C:/x/artwork.sqpreset" and n["name"].startswith("Artwork ") and "Alan Lee" in n["name"]
    assert [e["id"] for e in r["effects"]] == ["drop_shadow", "zoom_schnell", "fancy_out", "fancy_in"]
    sq = Path(img).with_name("q.jpg")
    Image.new("RGB", (800, 1200)).save(sq)
    assert pt.artwork(c, str(sq), 5.0)["nested"]["mask"].endswith("Maske Quadrat.png")


def test_artwork_only_opens_images(ctx, tmp_path):
    c, _ = ctx
    movie = tmp_path / "film.mp4"
    movie.write_bytes(b"x")
    with pytest.raises(ValueError, match="kein Bild"):
        pt.artwork(c, str(movie), 5.0)
    with pytest.raises(ValueError, match="nicht gefunden"):
        pt.artwork(c, str(tmp_path / "gibtsnicht.jpg"), 5.0)


def test_credit_text_from_filename_artist_db_and_override(ctx):
    c, img = ctx
    c.artist_db["ted nasmith"] = "Ted Nasmith"
    assert pt.credit_text_for(c, str(img), None, None) == "© alan lee"
    assert pt.credit_text_for(c, "x/Ted Nasmith - Armenelos.jpg", None, None) == "© ted nasmith"          # wie im Bau: immer klein
    assert pt.credit_text_for(c, None, "Artwork 03 Alan Lee - Hafen", None) == "© alan lee"          # Name einer Artwork-Sequenz
    assert pt.credit_text_for(c, None, "Hafen von Pelargir", None) == "© hafen von pelargir"        # aus dem Clipnamen
    assert pt.credit_text_for(c, str(img), None, "© Eigener Text") == "© Eigener Text"             # frei eingegebener Text bleibt unverändert


def test_credit_needs_a_template_and_writes_the_text_into_it(ctx, tmp_path):
    c, img = ctx
    with pytest.raises(ValueError, match="Vorlage"):
        pt.credit(c, art="artwork", path=str(img), name=None, text=None, dur=6.0)
    from test_mogrt_text import make_template, inspect, read_text
    c.credit_mogrt = {"artwork": str(make_template(tmp_path / "Credit Artwork v2.mogrt"))}
    r = pt.credit(c, art="artwork", path=str(img), name=None, text=None, dur=6.0)
    assert r["text"] == "© alan lee" and r["track"] == 9 and r["uebergang"] == pytest.approx(0.4167)
    assert read_text(inspect(Path(r["mogrt"]))[2]) == "© alan lee"
    assert r["png"] and Path(r["png"]).exists() and Path(r["png"]).suffix == ".png"    # Rückfall, falls Premiere die Grafik nicht lädt


def test_scene_at_finds_scene_from_the_latest_plan(ctx):
    c, _ = ctx
    c.plan = {"clips": [{"kind": "episode", "start": 0.0, "end": 10.0, "scene": "sz_01"}, {"kind": "episode", "start": 10.0, "end": 30.0, "scene": "sz_02"},
                        {"kind": "credit", "start": 12.0, "end": 14.0, "scene": "sz_02"}, {"kind": "anim", "start": 30.0, "end": 31.0, "scene": ""}]}
    c.scenes = {"sz_01": {"titel": "Schmiede", "status": "fertig"}, "sz_02": {"titel": "Hafen", "status": "neu"}}
    r = pt.scene_at(c, 12.5)
    assert r["scene"] == "sz_02" and r["titel"] == "Hafen" and r["start"] == 10.0 and r["end"] == 30.0
    assert pt.scene_at(c, 30.5)["scene"] == ""
    assert pt.scene_at(c, 999.0)["scene"] == ""
    c.plan = None
    with pytest.raises(ValueError, match="Rohschnitt"):
        pt.scene_at(c, 1.0)


def test_scene_start_for_seeking(ctx):
    c, _ = ctx
    c.plan = {"clips": [{"kind": "episode", "start": 10.0, "end": 30.0, "scene": "sz_02"}, {"kind": "credit", "start": 5.0, "end": 6.0, "scene": "sz_02"}]}
    assert pt.scene_start(c, "sz_02") == 5.0
    with pytest.raises(ValueError, match="nicht im Rohschnitt"):
        pt.scene_start(c, "sz_99")
