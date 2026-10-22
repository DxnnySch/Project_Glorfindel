from glorfindel.align_bullets import adopt_spoken, align_bullets, make_chunks
from glorfindel.config import Thresholds
from glorfindel.models import AssetRef, CommentBlock
from glorfindel.rough_cut import block_timing
from glorfindel.scenes import normalize_block, parse_bullets


def speak(text, t0, step=0.35):
    return [{"w": w, "start": round(t0 + i * step, 3), "end": round(t0 + i * step + 0.3, 3)}
            for i, w in enumerate(text.split())]


def transcript():
    tr = []
    tr += speak("Okay hallo zusammen und willkommen zu dieser Folge", 0)
    # Szene 1: erster Versuch abgebrochen, dann sauber (Retake nach langer Pause)
    tr += speak("also bei Celebrimbor in der Schmiede", 10)
    tr += speak("also bei Celebrimbor in der Schmiede sieht man dass er die Ringe nach Annatars Plänen fertigt", 30)
    tr += speak("und das erinnert stark an die Bücher wo Sauron das Feuer des Berges nutzt", 38)
    # Szene 2
    tr += speak("dann kommen wir nach Khazad-dûm wo Durin den Mithril findet", 60)
    return tr


UNITS = [
    ("sz_01", 0, ["Celebrimbor Schmiede Ringe Annatar", "Bücher Sauron Feuer Berg"]),
    ("sz_02", 0, ["Khazad-dûm Durin Mithril"]),
]


def test_chunks_split_on_pauses():
    assert len(make_chunks(transcript())) >= 4


def test_scene_regions_last_take_and_bullets():
    res = align_bullets(UNITS, transcript(), "r1")
    b1, b2 = res["sz_01"][0], res["sz_02"][0]
    assert b1["in"] >= 29.5 and b1["out"] < 59            # Retake bei 10 s verworfen, Take bei 30 s
    assert len(b1["takes"]) == 2 and b1["chosen"] == 1
    assert b2["in"] >= 59.5 and not b1.get("missing")
    sp = b1["stichpunkte"]
    assert sp[0]["in"] < sp[1]["in"] and sp[1]["in"] >= 38 - 0.1
    assert "Annatars" in b1["gesprochen"] and "hallo" not in b1["gesprochen"]
    assert b1["confidence"] == 1.0


def test_unmatched_block_is_missing():
    res = align_bullets([("sz_09", 0, ["Hobbits Pfeifenkraut Auenland"])] + UNITS, transcript(), "r1")
    assert res["sz_09"][0].get("missing")


def test_adopt_spoken_remaps_anchor_to_words():
    res = align_bullets(UNITS, transcript(), "r1")["sz_01"][0]
    blk = CommentBlock(modus="stichpunkte", stichpunkte=UNITS[0][2],
                       anker=[AssetRef(asset="a1", von=1, bis=None, einheit="stichpunkt")])
    adopt_spoken(blk, res)
    assert blk.modus == "text" and blk.anker[0].einheit == "wort"
    assert blk.text.split()[blk.anker[0].von] == "und"  # zweiter Stichpunkt beginnt mit „und das erinnert …“


def test_block_timing_for_bullets_estimated_and_aligned():
    th = Thresholds(bullet_seconds=10)
    blk = CommentBlock(modus="stichpunkte", stichpunkte=["a", "b", "c"])
    dur, starts = block_timing(blk, None, th)
    assert dur == 30 and starts == [0, 10, 20]
    al = {"in": 100.0, "out": 130.0,
          "stichpunkte": [{"idx": 0, "in": 100.0}, {"idx": 1, "in": 112.5}, {"idx": 2, "in": 121.0}]}
    dur, starts = block_timing(blk, al, th)
    assert dur == 30 and starts == [0, 12.5, 21.0]


def test_bullet_input_detected_in_text_field():
    assert parse_bullets("- Celebrimbor\n• Ringe\n2. Annatar") == ["Celebrimbor", "Ringe", "Annatar"]
    assert parse_bullets("Ein ganz normaler Satz.") == []
    b = normalize_block(CommentBlock(text="- eins\n- zwei"))
    assert b.modus == "stichpunkte" and b.stichpunkte == ["eins", "zwei"] and b.text == ""
