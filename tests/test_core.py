import pytest

from glorfindel import media, store
from glorfindel.config import Thresholds
from glorfindel.models import Anchor, Scene, Segment, Strand, CommentBlock
from glorfindel.paths import EpisodePaths, parse_slug, to_abs, to_rel
from glorfindel.scenes import (episode_report, scene_report, segment_light, sort_scenes,
                               speech_duration, validate_segments)
from glorfindel.timemap import TimeMap

from conftest import needs_ffmpeg


# ---- timemap ----
def test_identity_without_anchors():
    tm = TimeMap([])
    assert tm.is_identity and tm.ref_to_src(12.3) == 12.3


def test_single_anchor_is_offset():
    tm = TimeMap([Anchor(ref=10, src=13.4)])
    assert tm.ref_to_src(0) == pytest.approx(3.4)
    assert tm.src_to_ref(13.4) == pytest.approx(10)


def test_two_anchors_scale_and_offset():
    # Quelle läuft 4 % schneller (z. B. 25 -> 24 fps) und hat 2 s Vorlauf
    tm = TimeMap([(0, 2.0), (1000, 1042.0)])
    assert tm.ref_to_src(500) == pytest.approx(522.0)
    assert tm.src_to_ref(522.0) == pytest.approx(500)
    assert tm.ref_to_src(2000) == pytest.approx(2082.0)  # Extrapolation


def test_piecewise_three_anchors():
    tm = TimeMap([(0, 0), (100, 100), (200, 210)])
    assert tm.ref_to_src(50) == pytest.approx(50)
    assert tm.ref_to_src(150) == pytest.approx(155)
    assert tm.src_to_ref(155) == pytest.approx(150)
    assert len(tm.pieces_over(90, 110)) == 2


def test_duplicate_anchor_refs_do_not_crash():
    tm = TimeMap([(5, 5), (5, 6), (10, 12)])
    assert tm.ref_to_src(10) == pytest.approx(12)


# ---- scenes ----
def test_traffic_light():
    th = Thresholds()
    assert segment_light(5, th) == "gruen"
    assert segment_light(8, th) == "gelb"
    assert segment_light(9.6, th) == "rot"
    assert segment_light(9.5, th) == "gelb"


def test_scene_and_episode_report():
    th = Thresholds()
    sc = Scene(id="a", segmente=[Segment(**{"in": 0, "out": 5}), Segment(**{"in": 10, "out": 21})],
               kommentar=[CommentBlock(text="eins zwei drei vier fünf sechs sieben")])
    r = scene_report(sc, th)
    assert r["light"] == "rot" and r["montage"] and r["series_s"] == 16
    assert r["comment_s"] == pytest.approx(7 / th.words_per_second)
    ep = episode_report([sc], th)
    assert 0 < ep["series_share"] < 1


def test_validate_segments():
    bad = Scene(id="x", segmente=[Segment(**{"in": 5, "out": 5})])
    assert validate_segments(bad)


def test_sort_scenes_by_strand_with_fixed():
    strands = [Strand(id="b", name="B", order=0), Strand(id="a", name="A", order=1)]
    sc = [Scene(id="1", strang="a", reihenfolge=0), Scene(id="2", strang="b", reihenfolge=1, fixiert=True),
          Scene(id="3", strang="b", reihenfolge=2), Scene(id="4", strang="a", reihenfolge=3)]
    out = [s.id for s in sort_scenes(sc, strands)]
    assert out[1] == "2"            # fixiert bleibt an Position
    assert out == ["3", "2", "1", "4"]


def test_speech_duration():
    assert speech_duration("a b c d e f", Thresholds(words_per_second=2.0)) == 3.0


# ---- paths / store ----
def test_paths_roundtrip(tmp_path):
    root = tmp_path / "OD"
    (root / "x").mkdir(parents=True)
    f = root / "x" / "a.mp4"
    f.write_text("1")
    rel = to_rel(root, f)
    assert rel == "x/a.mp4" and to_abs(root, rel) == f
    assert parse_slug("S3 E1") == (3, 1) and parse_slug("foo") is None


def test_episode_paths_ensure(episode_root):
    ep = EpisodePaths(episode_root, 3, 1)
    ep.ensure()
    assert ep.scenes.is_dir() and ep.base.name == "S3 E1"


def test_atomic_write_and_lock(tmp_path):
    p = tmp_path / "a" / "b.json"
    store.write_json(p, {"x": "ä"})
    assert store.read_json(p) == {"x": "ä"}
    assert not list(p.parent.glob("*.tmp"))
    locks = tmp_path / "l"
    assert store.acquire_lock(locks, "sz_01", "maurice")["held"]
    other = store.acquire_lock(locks, "sz_01", "danny")
    assert not other["held"] and other["by"] == "maurice"
    store.release_lock(locks, "sz_01", "maurice")
    assert store.acquire_lock(locks, "sz_01", "danny")["held"]


def test_conflict_detection(tmp_path):
    (tmp_path / "sz_07.json").write_text("{}")
    (tmp_path / "sz_07-LAPTOP.json").write_text("{}")
    (tmp_path / "sz_08-OTHER.json").write_text("{}")  # Original fehlt -> keine Konfliktkopie
    c = store.find_conflicts(tmp_path)
    assert len(c) == 1 and c[0]["pc"] == "LAPTOP"


# ---- media ----
@needs_ffmpeg
def test_probe_and_proxy(clip, tmp_path):
    info = media.probe(clip)
    assert info["width"] == 320 and info["fps"] == pytest.approx(24, abs=0.01)
    assert info["duration"] == pytest.approx(6, abs=0.2)
    proxy = media.make_proxy(clip, tmp_path / "p" / "proxy.mp4", height=64)
    pinfo = media.probe(proxy)
    assert pinfo["height"] == 64


@needs_ffmpeg
def test_still_last_frame_and_fingerprint(clip, tmp_path):
    out = media.extract_still_last_frame(clip, 6.0, 24, tmp_path / "1.png", size=(640, 272))
    from PIL import Image
    assert Image.open(out).size == (640, 272)
    assert media.fingerprint(clip) == media.fingerprint(clip) != ""


@needs_ffmpeg
def test_waveform(clip):
    peaks = media.waveform_peaks(clip, buckets=100)
    assert 50 <= len(peaks) <= 100 and max(peaks) > 0.1
