"""Conform-Ausgabe muss echte konstante Bildrate haben (sonst lehnt Premiere den Dateitausch ab)."""
import json
import subprocess

import pytest

from glorfindel.conform import conform
from glorfindel.timemap import TimeMap
from test_conform import make_clip, needs_ffmpeg


def _video(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate,r_frame_rate,nb_frames",
                        "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)["streams"][0]


@needs_ffmpeg
@pytest.mark.parametrize("codec", ["prores", "h264"])
def test_conform_is_constant_frame_rate(tmp_path, codec):
    hq = make_clip(tmp_path / "hq.mp4", seconds=20, fps=25, size="320x136")
    tm = TimeMap([(0, 0.0), (6, 5.7), (12, 11.1), (18, 17.6)])           # stückweise andere Geschwindigkeiten
    out = conform(hq, tm, out_dur=19.0, dst=tmp_path / "c", codec=codec, fps=24000 / 1001)
    v = _video(out)
    num, den = (int(x) for x in v["avg_frame_rate"].split("/"))
    assert num / den == pytest.approx(24000 / 1001, abs=0.001), v
    assert v["avg_frame_rate"] == v["r_frame_rate"]
    assert int(v["nb_frames"]) == pytest.approx(19.0 * 24000 / 1001, abs=2)


def test_time_map_pure_offset():
    assert TimeMap([(10.0, 12.5)]).pure_offset() == pytest.approx(2.5)
    assert TimeMap([(0.0, 3.0), (100.0, 103.0)]).pure_offset() == pytest.approx(3.0)
    assert TimeMap([(0.0, 3.0), (100.0, 104.0)]).pure_offset() is None            # Tempoänderung


@needs_ffmpeg
def test_reference_offset_shifts_timeline(tmp_path):
    from glorfindel import media
    from glorfindel.premiere_media import conform_reference
    src = make_clip(tmp_path / "s.mp4", seconds=6, fps=24, size="320x136")
    out = conform_reference(src, tmp_path / "r.mp4", fps=24.0, size=(320, 136), offset=2.0)
    assert media.probe(out)["duration"] == pytest.approx(8.0, abs=0.2)
    cut = conform_reference(src, tmp_path / "c.mp4", fps=24.0, size=(320, 136), offset=-1.0)
    assert media.probe(cut)["duration"] == pytest.approx(5.0, abs=0.2)
