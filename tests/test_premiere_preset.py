import pytest

from glorfindel.premiere_preset import find_base_preset, make_sequence_preset, read_preset_counts

SAMPLE = """﻿<?xml version="1.0" encoding="UTF-8"?>
<PremiereData Version="3">
\t<SequencePreset ObjectID="1" ClassID="5e73dd7e" Version="1">
\t\t<InitialNumberOfFiveOneTracks>3</InitialNumberOfFiveOneTracks>
\t\t<InitialNumberOfStereoTracks>3</InitialNumberOfStereoTracks>
\t\t<InitialNumberOfVideoTracks>3</InitialNumberOfVideoTracks>
\t\t<VideoFrameSize>0,0,1920,1080</VideoFrameSize>
\t\t<VideoFrameRate>4237833600</VideoFrameRate>
\t</SequencePreset>
</PremiereData>
"""


def test_preset_gets_requested_tracks_and_exact_60_fps(tmp_path):
    base = tmp_path / "base.sqpreset"
    base.write_text(SAMPLE, encoding="utf-8")
    out = make_sequence_preset(tmp_path / "x" / "rohschnitt.sqpreset", video_tracks=14, audio_tracks=16, base=base)
    assert read_preset_counts(out) == {"video": 14, "audio": 16, "fps": pytest.approx(60.0)}
    xml = out.read_text(encoding="utf-8-sig")
    assert "<InitialNumberOfFiveOneTracks>0<" in xml and "1920,1080" in xml and out.read_bytes()[:3] == b"\xef\xbb\xbf"


def test_unexpected_preset_is_rejected(tmp_path):
    bad = tmp_path / "bad.sqpreset"
    bad.write_text("<x/>", encoding="utf-8")
    with pytest.raises(ValueError):
        make_sequence_preset(tmp_path / "o.sqpreset", video_tracks=5, audio_tracks=5, base=bad)


def test_real_adobe_preset_if_installed(tmp_path):
    base = find_base_preset()
    if base is None:
        pytest.skip("Premiere nicht installiert")
    out = make_sequence_preset(tmp_path / "r.sqpreset", video_tracks=14, audio_tracks=16)
    c = read_preset_counts(out)
    assert c["video"] == 14 and c["audio"] == 16 and c["fps"] == pytest.approx(60.0, abs=0.001)
    assert "1920,1080" in out.read_text(encoding="utf-8-sig")
