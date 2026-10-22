import pytest

from glorfindel import media
from glorfindel.conform import (build_filtergraph, compare_frames, conform, plan_segments,
                                render_stills_from_hq)
from glorfindel.timemap import TimeMap

from conftest import make_clip, needs_ffmpeg


def test_plan_pure_offset_leading_black():
    # HQ beginnt 2 s später als die Schnittquelle: ref 0..2 -> Schwarz, danach HQ ab 0
    tm = TimeMap([(2.0, 0.0)])
    segs = plan_segments(tm, out_dur=10, hq_dur=6)
    assert (segs[0].hq0, segs[0].dur) == (None, pytest.approx(2.0))
    assert segs[1].hq0 == pytest.approx(0) and segs[1].hq1 == pytest.approx(6)
    assert segs[-1].hq0 is None and segs[-1].out1 == pytest.approx(10)  # Rest schwarz
    assert sum(s.dur for s in segs) == pytest.approx(10)


def test_plan_hq_starts_earlier_than_ref():
    tm = TimeMap([(0.0, 3.0)])  # HQ hat 3 s Vorlauf, wird abgeschnitten
    segs = plan_segments(tm, out_dur=4, hq_dur=20)
    assert len(segs) == 1 and segs[0].hq0 == pytest.approx(3) and segs[0].hq1 == pytest.approx(7)


def test_plan_tempo_change():
    tm = TimeMap([(0, 0), (100, 104)])
    segs = plan_segments(tm, out_dur=50, hq_dur=500)
    assert segs[0].a == pytest.approx(1.04) and segs[0].hq1 == pytest.approx(52)


def test_filtergraph_contains_expected_parts():
    segs = plan_segments(TimeMap([(2.0, 0.0)]), 5, 3)
    fg, out = build_filtergraph(segs, (320, 136), 24)
    assert "color=c=black" in fg and "concat=n=2" in fg and "[aout]" in fg


@needs_ffmpeg
def test_conform_offset_and_length(tmp_path):
    hq = make_clip(tmp_path / "hq.mp4", seconds=6, fps=25, size="640x272")
    out = conform(hq, TimeMap([(2.0, 0.0)]), out_dur=8.0, dst=tmp_path / "c", codec="h264", fps=24)
    info = media.probe(out)
    assert info["duration"] == pytest.approx(8.0, abs=0.15)
    assert info["fps"] == pytest.approx(24, abs=0.01) and info["width"] == 640
    # Am Anfang schwarz, nach 3 s Bild
    media.extract_frame(out, 0.5, tmp_path / "f0.png")
    media.extract_frame(out, 3.0, tmp_path / "f3.png")
    from PIL import Image
    import numpy as np
    assert np.asarray(Image.open(tmp_path / "f0.png").convert("L")).mean() < 5
    assert np.asarray(Image.open(tmp_path / "f3.png").convert("L")).mean() > 40


@needs_ffmpeg
def test_conform_tempo_and_frame_match(tmp_path):
    """Quelle läuft in HQ 4 % schneller: nach Conform muss derselbe Inhalt zur selben Zeit liegen."""
    ref = make_clip(tmp_path / "ref.mp4", seconds=10, fps=24, size="320x136")
    hq = make_clip(tmp_path / "hq.mp4", seconds=10, fps=24, size="320x136")  # gleicher Inhalt
    # Vortäuschen einer abweichenden Laufgeschwindigkeit: ref_t=5 entspricht hq_t=5.2
    tm = TimeMap([(0, 0), (5, 5.2)])
    out = conform(hq, tm, out_dur=9.0, dst=tmp_path / "c", codec="h264", fps=24)
    assert media.probe(out)["duration"] == pytest.approx(9.0, abs=0.15)
    cmp = compare_frames(out, 5.0, hq, 5.2, tmp_path / "cmp")
    assert cmp["correlation"] > 0.95


@needs_ffmpeg
def test_stills_from_hq_same_names(tmp_path):
    hq = make_clip(tmp_path / "hq.mp4", seconds=6)
    out = render_stills_from_hq(hq, TimeMap([(1.0, 0.0)]), {"1.png": 4.0, "2.png": 6.0}, tmp_path / "hqstills", 24)
    assert sorted(out) == ["1.png", "2.png"] and all(p.exists() for p in out.values())


@needs_ffmpeg
def test_compare_detects_mismatch(tmp_path):
    a = make_clip(tmp_path / "a.mp4", seconds=6)
    cmp_same = compare_frames(a, 3.0, a, 3.0, tmp_path / "c1")
    cmp_off = compare_frames(a, 1.0, a, 5.0, tmp_path / "c2")
    assert cmp_same["correlation"] > 0.99 and not cmp_same["uncertain"]
    assert cmp_off["correlation"] < cmp_same["correlation"]
