import subprocess
from pathlib import Path

import pytest
from PIL import Image

from glorfindel import media
from glorfindel.conform import compare_frames
from glorfindel.premiere_media import FRAME, credit_png, conform_reference

from conftest import needs_ffmpeg


@needs_ffmpeg
def test_conform_reference_makes_cfr_cropped_and_keeps_timeline(tmp_path):
    # Bildschirmmitschnitt-Ersatz: variable Bildrate (Frames fallen unregelmäßig), Letterbox oben/unten
    src = tmp_path / "screen.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=8",
                    "-f", "lavfi", "-i", "sine=frequency=330:duration=8", "-vf",
                    "drawbox=x=0:y=0:w=640:h=40:color=black:t=fill,drawbox=x=0:y=320:w=640:h=40:color=black:t=fill,select='not(eq(mod(n,7),3))'",
                    "-fps_mode", "vfr", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)], check=True)
    out = conform_reference(src, tmp_path / "ref_cfr.mp4", crop=[0, 40, 640, 280], size=(960, 420))
    info = media.probe(out)
    assert info["width"] == 960 and info["height"] == 420 and info["fps"] == pytest.approx(23.976, abs=0.01)
    assert info["duration"] == pytest.approx(media.probe(src)["duration"], abs=0.3) and info["has_audio"]
    cmp = compare_frames(out, 3.0, src, 3.0, tmp_path / "c", crop_b=[0, 40, 640, 280])     # gleiche Zeit, gleicher Inhalt
    assert cmp["correlation"] > 0.9


@needs_ffmpeg
def test_stills_use_the_frame_before_the_cut(tmp_path):
    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x136:rate=24:duration=4", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    last = media.extract_still_last_frame(clip, 2.0, 24, tmp_path / "a.png")           # letzter Frame vor 2,0 s = Frame 47
    ref = media.extract_frame(clip, 47 / 24 + 0.005, tmp_path / "b.png")
    nxt = media.extract_frame(clip, 48 / 24 + 0.005, tmp_path / "n.png")
    import numpy as np
    a, b, n = (np.asarray(Image.open(p).convert("L"), dtype=float) for p in (last, ref, nxt))
    assert abs(a - b).mean() < 0.5 and abs(a - n).mean() > 0.5                          # exakt der Frame vor dem Schnitt


def test_credit_png_positions_and_style(tmp_path):
    art = Image.open(credit_png("© alan lee", "artwork", tmp_path))
    ama = Image.open(credit_png("© amazon studios", "amazon", tmp_path))
    mus = Image.open(credit_png("© scott buckley - i walk with ghosts", "musik", tmp_path))
    assert art.size == ama.size == FRAME and art.mode == "RGBA"
    def box(im):
        return im.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
    ba, bm, bu = box(art), box(ama), box(mus)
    assert abs((ba[0] + ba[2]) / 2 - 960) < 6 and ba[1] < 200                            # oben mittig
    assert bm[0] < 120 and bm[3] > 950                                                    # unten links
    assert bu[2] > 1800 and bu[3] > 950                                                   # unten rechts
    assert credit_png("© alan lee", "artwork", tmp_path) == credit_png("© alan lee", "artwork", tmp_path)   # wiederverwendet
    px = [p for p in art.getdata() if p[3] > 250]
    assert px and all(p[:3] == (255, 255, 255) for p in px[:50])                          # weiße Schrift
    left = Image.open(credit_png("© alan lee", "artwork", tmp_path, x_override=0.27))
    assert box(left)[2] < 960
