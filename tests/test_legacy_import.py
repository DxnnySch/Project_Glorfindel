from pathlib import Path

import pytest
from docx import Document

from glorfindel.legacy_import import is_frame_cue, parse_legacy_script

REAL = Path("F:/OneDrive/Mythen-Archiv/Videos/S2 E7/Script-Quellen/S2 E7 Script.docx")


def make_doc(path, lines):
    d = Document()
    for ln in lines:
        d.add_paragraph(ln)
    d.save(str(path))


def test_cues_speakers_free_blocks(tmp_path):
    p = tmp_path / "s.docx"
    make_doc(p, [
        "P: Wir haben die siebte Folge geschaut.", "Abo nicht vergessen.",
        "[Intro]", "Werbetext hier.",
        "[Celebrimbor auf Balkon]", "P: Die Folge beginnt in Eregion.", "Zweiter Absatz.",
        "D: Hier befiehlt Annatar.",
        "[„They have a Ravager“]", "Dieser Rammbock ist wie Grond.",
        "[Stichpunkt-Szene]", "- Durin\n- Mithril",
        "[CREDITS]", "D: Bis zum nächsten Mal!",
    ])
    r = parse_legacy_script(p)
    sc = r["scenes"]
    assert [s.titel for s in sc] == ["Celebrimbor auf Balkon", "„They have a Ravager“", "Stichpunkt-Szene"]
    assert [(b.sprecher, b.text) for b in sc[0].kommentar] == [
        ("philipp", "Die Folge beginnt in Eregion. Zweiter Absatz."), ("danny", "Hier befiehlt Annatar.")]
    assert sc[1].kommentar[0].sprecher == "danny"                      # Sprecher bleibt bis zum Wechsel
    assert sc[2].kommentar[0].modus == "stichpunkte" and sc[2].kommentar[0].stichpunkte == ["Durin", "Mithril"]
    fb = r["free_blocks"]
    assert [(f["titel"], f["after"]) for f in fb] == [("Cold Open", None), ("Intro", None), ("CREDITS", "sz_03")]
    assert "Abo nicht" in fb[0]["text"] and "Bis zum nächsten Mal" in fb[2]["text"]


def test_frame_cue_detection():
    assert is_frame_cue("Intro") and is_frame_cue("CREDITS") and is_frame_cue("Werbung")
    assert not is_frame_cue("Celebrimbor perfektioniert Ringe – bemerkt Time-loop der Vision")


@pytest.mark.skipif(not REAL.exists(), reason="echtes Skript nicht verfügbar")
def test_real_script_s2e7():
    r = parse_legacy_script(REAL)
    st = r["stats"]
    assert 40 <= st["scenes"] <= 50 and st["free_blocks"] >= 2 and st["words"] > 1500
    assert {b.sprecher for s in r["scenes"] for b in s.kommentar} == {"philipp", "danny"}
    assert all(s.kommentar for s in r["scenes"] if s.titel)  # jede Szene hat Text
