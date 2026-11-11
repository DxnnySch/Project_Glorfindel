"""HQ-Modus: Vorschau-Proxy aus der HQ-Datei (zeitgleich zur Referenz), Untertitel der HQ-Datei zuerst."""
import pytest

from glorfindel import dialog, media
from glorfindel.models import Anchor
from glorfindel.service import Episode

from conftest import make_clip, needs_ffmpeg


@pytest.fixture
def ep(episode_root):
    e = Episode.create(episode_root, 3, 2, "Test")
    e.import_source(make_clip(e.p.root / "Filme" / "ref.mp4", seconds=6, size="320x136"))
    hq = e.import_source(make_clip(e.p.root / "Filme" / "hq.mp4", seconds=8, size="640x272", tone=880), role="hq")
    (e.p.root / "Filme" / "hq.de.srt").write_text("1\n00:00:03,000 --> 00:00:04,000\nHallo Welt\n", encoding="utf-8")
    (e.p.root / "Filme" / "ref.en.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHello world\n", encoding="utf-8")
    return e, hq


def test_hq_source_found_and_mode_default_off(ep):
    e, hq = ep
    assert e.hq_source().id == hq.id
    assert e.project().hq_modus is False
    assert e.view_proxy_path("q1") == e.proxy_path("q1")


def test_hq_subtitles_first_only_in_hq_mode(ep):
    e, hq = ep
    assert dialog.subtitle_candidates(e)[0]["source"] == "q1"
    pr = e.project(); pr.hq_modus = True; e.save_project(pr)
    assert dialog.subtitle_candidates(e)[0]["source"] == hq.id


def test_hq_proxy_needs_anchor(ep):
    e, _ = ep
    with pytest.raises(RuntimeError, match="Anker"):
        e.ensure_hq_proxy()


@needs_ffmpeg
def test_hq_proxy_is_aligned_to_reference_and_served(ep):
    e, hq = ep
    e.set_anchors(hq.id, [Anchor(ref=0, src=1.0)])          # HQ hat 1 s Vorlauf
    out = e.ensure_hq_proxy()
    info = media.probe(out)
    assert info["duration"] == pytest.approx(6, abs=0.3)    # Länge der Referenz, nicht der HQ-Datei
    assert info["height"] == 540
    pr = e.project(); pr.hq_modus = True; e.save_project(pr)
    assert e.view_proxy_path("q1") == out                    # Player bekommt im HQ-Modus den HQ-Proxy
    pr.hq_modus = False; e.save_project(pr)
    assert e.view_proxy_path("q1") == e.proxy_path("q1")
