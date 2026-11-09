"""Untertitel (SRT/VTT/TTML) als Dialog der Episode statt Transkription."""
from glorfindel import dialog, subtitles
from glorfindel.models import Anchor
from glorfindel.service import Episode
from glorfindel.timemap import TimeMap
from conftest import make_clip, needs_ffmpeg

SRT = """1
00:00:01,000 --> 00:00:03,000
<i>Guten Abend</i>, Elrond.

2
00:00:04,000 --> 00:00:06,000
[Musik]

3
00:00:07,500 --> 00:00:09,500
- Wer geht dort?
- Ein Freund.
"""
TTML = """<?xml version="1.0" encoding="UTF-8"?>
<tt xmlns="http://www.w3.org/ns/ttml" xmlns:tts="http://www.w3.org/ns/ttml#styling" ttp:tickRate="10000000" xmlns:ttp="http://www.w3.org/ns/ttml#parameter">
<body><div>
<p begin="10000000t" end="30000000t">Guten<br/>Abend</p>
<p begin="00:00:05.500" end="00:00:07.000"><span>Hallo</span> Welt</p>
</div></body></tt>"""


def test_parse_srt_cleans_tags_and_sounds():
    cues = subtitles.parse_text_cues(SRT)
    assert [c[2] for c in cues] == ["Guten Abend, Elrond.", "Wer geht dort? Ein Freund."]
    assert cues[0][:2] == (1.0, 3.0)


def test_parse_ttml_ticks_and_clock(tmp_path):
    f = tmp_path / "x.dfxp"
    f.write_text(TTML, encoding="utf-8")
    cues = subtitles.parse_file(f)
    assert cues[0] == (1.0, 3.0, "Guten Abend") and cues[1] == (5.5, 7.0, "Hallo Welt")


def test_words_use_timemap_and_stay_in_cue():
    tm = TimeMap([Anchor(ref=0, src=3.4), Anchor(ref=100, src=103.4)])      # Quelle = Episodenzeit + 3,4 s
    words = subtitles.cues_to_words([(10.0, 12.0, "Guten Abend")], tm)
    assert [w["w"] for w in words] == ["Guten", "Abend"]
    assert abs(words[0]["start"] - 6.6) < 1e-6 and abs(words[-1]["end"] - 8.6) < 1e-6
    assert all(a["end"] <= b["start"] + 1e-9 for a, b in zip(words, words[1:]))


def test_language_and_candidates_prefers_german(tmp_path):
    v = tmp_path / "Folge 7.mp4"
    v.write_bytes(b"")
    for n in ("Folge 7.en.srt", "Folge 7.de.srt", "Anderes.de.srt"):
        (tmp_path / n).write_text(SRT)
    got = subtitles.find_candidates(v)
    assert [g.name for g in got] == ["Folge 7.de.srt", "Folge 7.en.srt"]
    assert subtitles.language_of(got[0]) == "de"


@needs_ffmpeg
def test_transcribe_uses_subtitles_without_whisper(episode_root, tmp_path):
    ep = Episode.create(episode_root, 2, 7)
    ref = make_clip(tmp_path / "OneDrive" / "Folge 7.mp4")
    (ref.parent / "Folge 7.de.srt").write_text(SRT, encoding="utf-8")
    src = ep.import_source(str(ref), "referenz")
    out = dialog.transcribe(ep, None, "auto", None)      # kein Whisper, kein Schlüssel nötig
    assert out["datei"] == "Folge 7.de.srt" and out["words"] == 8
    d = dialog.load(ep)
    assert d["quelle"] == src.id and d["words"][0]["w"] == "Guten"
    assert dialog.text_between(d["words"], 0.5, 3.5).startswith("Guten Abend")
