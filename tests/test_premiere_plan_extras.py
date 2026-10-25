"""Pause/Play-Dateien, Schwarzstreifen, Artwork-Sequenzen, Karten-Animation, Amazon-Credit vs. Künstler-Credit."""
import subprocess

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
    assert n["mask_scale"] == round(1000 / 800 * 100, 3)
    assert all("media" in c for c in plan["clips"] if c["kind"] == "anim")
    bars = [c for c in plan["clips"] if c["kind"] == "bars"]
    assert len(bars) == 1 and bars[0]["track"] == 7
    assert {c["kind"] for c in plan["clips"] if c["kind"] == "adjust"} == {"adjust"}
