"""Reihenfolge wie in der Aufnahme: Szenen/Blöcke nach Aufnahmezeit, Gesprochenes ohne Skript (Zwischenstücke) bleibt erhalten."""
import pytest

from glorfindel.config import Thresholds
from glorfindel.extras import find_extras
from glorfindel.models import CommentBlock, Scene, Segment
from glorfindel.rough_cut import build_package, load_template, order_by_audio

TH, TPL = Thresholds(), load_template()
A = "Galadriel sucht in den Ruinen von Eregion nach den Spuren des Dunklen Herrschers"
B = "Sauron aber wartet längst in Mordor auf den richtigen Moment um zuzuschlagen"


def words(text, t0):
    out, t = [], t0
    for w in text.split():
        out.append({"w": w, "start": round(t, 2), "end": round(t + 0.3, 2)})
        t += 0.35
    return out, t


def transcript():
    """Aufnahme: Begrüßung, B, Überleitung, A, Retake von A (Versprecher), Schluss."""
    tr, t = [], 0.0
    for text in ["Hallo ihr Lieben heute geht es los", B, "und jetzt kommen wir zum nächsten Punkt", A, A, "das war es für heute bis bald"]:
        w, t = words(text, t + 1.5)   # Sprechpausen zwischen den Teilen
        tr += w
    return tr


def seg(a, b):
    return Segment(**{"in": a, "out": b})


def scenes():
    return [Scene(id="sz_01", titel="A", segmente=[seg(100, 106)], kommentar=[CommentBlock(sprecher="philipp", text=A)]),
            Scene(id="sz_02", titel="B", segmente=[seg(300, 306)], kommentar=[CommentBlock(sprecher="philipp", text=B)])]


def alignment(tr):
    from glorfindel import align
    res = align.align_recording([("sz_01", 0, A), ("sz_02", 0, B)], tr, "r1", prefer="first")
    al = {"recordings": [{"id": "r1", "speaker": "philipp", "path": "rec.wav"}], "scenes": res}
    ivs = [(b["in"], b["out"], (sid, b["block"])) for sid, bl in res.items() for b in bl]
    al["zusatz"] = [{**x, "rec": "r1", "speaker": "philipp"} for x in find_extras(tr, ivs, [A, B])]
    return al


def test_extras_found_between_blocks_retake_dropped():
    al = alignment(transcript())
    texts = [z["text"] for z in al["zusatz"]]
    assert texts == ["Hallo ihr Lieben heute geht es los", "und jetzt kommen wir zum nächsten Punkt", "das war es für heute bis bald"]
    assert [z["after"] for z in al["zusatz"]] == [None, ["sz_02", 0], ["sz_01", 0]]   # Wiederholung von A ist kein Zwischenstück


def test_scenes_follow_the_recording():
    al = alignment(transcript())
    assert [s.id for s in order_by_audio(scenes(), al)] == ["sz_02", "sz_01"]          # in der Aufnahme kommt B vor A


def test_package_keeps_extras_in_recording_order():
    al = alignment(transcript())
    p = build_package(scenes(), slug="S3 E1", template=TPL, th=TH, alignment=al, audio_order=True)
    voice = sorted((c for c in p["tracks"][TPL["tracks"]["speaker_audio"]["philipp"]] if c["type"] == "comment"), key=lambda c: c["start"])
    # Aufnahmezeit steigt über den ganzen Schnitt: Begrüßung, B, Überleitung, A, Schluss
    src_in = [c["src_in"] for c in voice]
    assert src_in == sorted(src_in) and len(voice) == 5
    assert [bool(c.get("extra")) for c in voice] == [True, False, True, False, True]
    assert [s["scene"] for s in p["tracks"]["V1"] if s["type"] == "scene_segment"] == ["sz_02", "sz_01"]


def test_without_option_nothing_changes():
    al = alignment(transcript())
    p = build_package(scenes(), slug="S3 E1", template=TPL, th=TH, alignment=al)
    voice = [c for c in p["tracks"][TPL["tracks"]["speaker_audio"]["philipp"]] if c["type"] == "comment"]
    assert len(voice) == 2 and not any(c.get("extra") for c in voice)
    assert [s["scene"] for s in p["tracks"]["V1"] if s["type"] == "scene_segment"] == ["sz_01", "sz_02"]
