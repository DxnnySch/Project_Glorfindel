"""Pause/Play-Dateien, Schwarzstreifen, Artwork-Sequenzen, Karten-Animation, Amazon-Credit vs. Künstler-Credit."""
import subprocess

import pytest

from PIL import Image

from glorfindel import premiere_media
from glorfindel.premiere_plan import _amazon_vs_artist, _map_effect
from plan_fixture import make_plan


def test_amazon_credit_is_cut_at_artist_credits():
    clips = [{"kind": "credit", "art": "amazon", "start": 0.0, "end": 20.0, "track": 8},
             {"kind": "credit", "art": "artwork", "start": 5.0, "end": 8.0, "track": 9},
             {"kind": "credit", "art": "artwork", "start": 7.0, "end": 12.0, "track": 12}]
    _amazon_vs_artist(clips)
    amazon = sorted((c["start"], c["end"]) for c in clips if c["art"] == "amazon")
    assert amazon == [(0.0, 5.0), (12.0, 20.0)]


def test_amazon_pieces_keep_exact_frame_times():
    """Test10.prproj: Credit-Zeiten auf 4 Stellen gerundet (25.0667 statt 1504/60) – Premiere setzte das Ende genau, fügte die nächste Vorlage
    aber auf dem Bildraster ein: hauchdünne Reste des vorigen Credits blieben stehen und wurden mitverschoben."""
    t = 1504 / 60
    clips = [{"kind": "credit", "art": "amazon", "start": 0.0, "end": 2000 / 60, "track": 8},
             {"kind": "credit", "art": "artwork", "start": t, "end": 1800 / 60, "track": 9}]
    _amazon_vs_artist(clips)
    amazon = sorted((c["start"], c["end"]) for c in clips if c["art"] == "amazon")
    assert amazon == [(0.0, t), (1800 / 60, 2000 / 60)]                   # genau, nicht 25.0667


def test_map_effect_slides_in_and_out():
    fx = _map_effect(10.0)
    kfs = fx["params"][0]["keyframes"]
    assert [t for t, _ in kfs] == [0.0, 0.5, 9.5, 10.0]
    assert kfs[0][1]["point"] == [0.5, -0.5] and kfs[1][1]["point"] == [0.5, 0.5]
    assert _map_effect(0.8) is None


def test_bars_png_has_transparent_middle(tmp_path):
    p = premiere_media.bars_png(tmp_path / "b.png")
    im = Image.open(p).convert("RGBA")
    assert im.size == (1920, 1080)
    assert im.getpixel((960, 10)) == (0, 0, 0, 255) and im.getpixel((960, 1070)) == (0, 0, 0, 255)
    assert im.getpixel((960, 540))[3] == 0
    assert im.getpixel((960, 139))[3] == 255 and im.getpixel((960, 141))[3] == 0


def test_play_is_pause_reversed(tmp_path):
    src = tmp_path / "Pause.mov"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=1", "-c:v", "prores_ks",
                    "-profile:v", "4444", "-pix_fmt", "yuva444p10le", str(src)], check=True)
    pause, play = premiere_media.play_pause_clips(src, tmp_path / "anim")
    assert pause == src and play.exists()

    def frame(path, t):
        out = tmp_path / f"f{t}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1", str(out)], check=True)
        return Image.open(out).convert("RGB").tobytes()

    diff = lambda a, b: sum(abs(x - y) for x, y in zip(a, b)) / len(a)  # noqa: E731 – ProRes ist verlustbehaftet
    assert diff(frame(play, 0), frame(src, 0.9)) < 3 and diff(frame(play, 0), frame(src, 0)) > 10


def test_plan_has_nested_artworks_and_anim_media():
    plan = make_plan()
    art = [c for c in plan["clips"] if c["kind"] == "artwork"]
    assert art and all("nested" in c and "crop" not in c for c in art)
    names = [n["name"] for n in plan["nested"]]
    assert len(set(names)) == len(names), "Namen der Artwork-Sequenzen eindeutig"
    n = plan["nested"][0]
    assert (n["image_track"], n["mask_track"], n["matte_track"]) == (2, 4, 5)
    # Alle Bilder der Fixture liegen als Doppelbild nebeneinander: immer die abgerundete Quadrat-Maske (Querformat-Wahl: pick_mask-Test unten)
    assert all(x["mask_name"] == "Maske Quadrat.png" and x["mask_scale"] == 83.7 for x in plan["nested"])
    assert all("media" in c for c in plan["clips"] if c["kind"] == "anim")
    bars = [c for c in plan["clips"] if c["kind"] == "bars"]
    assert len(bars) == 1 and bars[0]["track"] == 7
    assert {c["kind"] for c in plan["clips"] if c["kind"] == "adjust"} == {"adjust"}


def _library():
    import json
    from pathlib import Path
    return json.loads((Path(__file__).resolve().parents[1] / "vorlagen" / "effekt_bibliothek.json").read_text(encoding="utf-8"))


def test_library_matches_the_measured_original_values():
    lib = _library()
    assert {"fancy_in", "fancy_out", "zoom_schnell", "zoom_langsam", "karte_in", "karte_out", "gauss_in", "gauss_out"} <= set(lib)
    rahmen = lambda r: next(p for p in lib[r]["params"] if p["name"] == "Rahmen")["keyframes"]  # noqa: E731
    assert rahmen("fancy_in") == [[0.0, 500.0], [0.5, 8.0]]
    assert [t for t, _ in rahmen("fancy_out")] == [-0.5333, -0.5167, -0.0167]          # wie im Ursprungsschnitt gemessen
    assert lib["fancy_out"]["anchor"] == "end" and lib["fancy_in"]["anchor"] == "start" and lib["zoom_schnell"]["anchor"] == "start"
    zoom = next(p for p in lib["zoom_schnell"]["params"] if p["name"] == "Skalierungshöhe")["keyframes"]
    assert zoom == [[0.0, 100.0], [120.0, 240.0]]
    assert lib["karte_in"]["anchor"] == "start" and lib["karte_out"]["anchor"] == "end"
    pos = next(p for p in lib["karte_in"]["params"] if p["name"] == "Position")["keyframes"]
    assert pos[0][1]["point"][1] < -0.5 and pos[1][1]["point"] == [0.5, 0.5]


def test_real_preset_folder_agrees_with_snapshot():
    import pytest
    from pathlib import Path
    from glorfindel import prfpset
    folder = Path(r"F:\OneDrive\Videomaterial\Programm-Vorgaben\PremierePro")
    if not folder.exists():
        pytest.skip("Vorgaben-Ordner nur auf Dannys Rechner")
    assert prfpset.effect_library(folder) == _library()


def test_map_and_artwork_effects_come_from_the_library():
    from glorfindel.premiere_plan import _resolve_chain, load_recipes, with_library
    rec = with_library(load_recipes(), _library())
    chain = _resolve_chain(rec, [{"recipe": "karte_in"}, {"recipe": "karte_out"}], 10.0, None, 60.0)
    assert [c["id"] for c in chain] == ["karte_in", "karte_out"]
    out_kf = next(p for p in chain[1]["params"] if p["name"] == "Position")["keyframes"]
    assert [t for t, _ in out_kf] == [9.4833, 9.9833]
    assert rec["blur"]["match_name"] == "AE.Impact_Blur_FX" and rec["blur"]["ein"]["param"] == "Stärke"
    zoom = _resolve_chain(rec, [{"recipe": "zoom_schnell"}], 5.0, None, 60.0)[0]
    assert next(p for p in zoom["params"] if p["name"] == "Skalierungshöhe")["keyframes"][-1] == [120.0, 240.0]


def test_autoframe_picks_masks_and_keeps_subject_visible():
    from glorfindel import autoframe
    assert autoframe.pick_mask((1920, 1080)) == "Maske.png" and autoframe.pick_mask((600, 500)) == "Maske Quadrat.png"
    assert autoframe.pick_mask((800, 1200)) == "Maske Quadrat.png"
    fr = autoframe.frame_image((800, 1200), "Maske Quadrat.png", 1150, {"x0": 0.3, "y0": 0.05, "x1": 0.7, "y1": 0.35})
    x0, y0, x1, y1 = fr["region"]
    assert x0 <= 0.3 and y0 <= 0.05 and x1 >= 0.7 and y1 >= 0.35 and 0 <= x0 and x1 <= 1 and 0 <= y0 and y1 <= 1   # Motiv im Ausschnitt, Ausschnitt im Bild
    # Bild deckt die sichtbare Maske: Bildhälfte (in Bildschirmpixeln) ≥ Maskenhälfte
    s = fr["image_scale"] / 100
    assert 800 * s >= 1150 and 1200 * s >= 1000
    # möglichst viel Bild: der Ausschnitt ist der größte mit dem Seitenverhältnis der Maske
    assert (y1 - y0) * 1200 == pytest.approx(800 / (920 / 800), abs=2) and (x1 - x0) == pytest.approx(1.0, abs=1e-3)
    # Bild fast im Seitenverhältnis der Maske: (fast) alles bleibt sichtbar
    full = autoframe.frame_image((600, 500), "Maske Quadrat.png", 1150, {"x0": 0.4, "y0": 0.3, "x1": 0.6, "y1": 0.6})
    assert full["region"][2] - full["region"][0] > 0.95 and full["region"][3] - full["region"][1] > 0.99
    # ohne Motiv: mittiger Ausschnitt
    mid = autoframe.frame_image((1920, 1080), "Maske.png", 1536, None)
    assert mid["image_position"][0] == 0.5 and mid["mask_scale"] == 80.0
    # Doppelbild: Mitte der Maske im Rahmen verschoben, Bild folgt
    left = autoframe.frame_image((600, 500), "Maske Quadrat.png", 500, None, center=(0.27, 0.5))
    assert left["mask_position"] == [0.27, 0.5] and left["image_position"] == [0.27, 0.5]


def test_subject_box_normalizes_vision_model_output(tmp_path):
    from glorfindel import autoframe

    class Msg:
        content = '{"x0": 100, "y0": 50, "x1": 900, "y1": 950}'

    class Resp:
        choices = [type("C", (), {"message": Msg})]

    class Client:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                def create(**kw):
                    return Resp

    class FakeLlm:
        last_error = ""
        client = Client

        def enabled(self, f):
            return True

        def model_for(self, f):
            return "alias-vision"

    img = tmp_path / "a.png"
    Image.new("RGB", (400, 300), (10, 20, 30)).save(img)
    box = autoframe.subject_box(FakeLlm(), img, tmp_path / "cache.json")
    assert box == {"x0": 0.1, "y0": 0.05, "x1": 0.9, "y1": 0.95}
    assert autoframe.subject_box(None, img) is None
    assert (tmp_path / "cache.json").exists()                      # zweite Anfrage kommt aus dem Zwischenspeicher
