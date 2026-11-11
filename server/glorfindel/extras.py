"""Zwischenstücke einer Aufnahme: alles Gesprochene, das in keinem Skriptblock steht (Begrüßung, Überleitungen, Schluss).

Der Abgleich findet die Skriptblöcke in der Aufnahme; hier werden die Lücken dazwischen untersucht. Wiederholte Versuche
(Versprecher, die so im Skript stehen) sind keine Zwischenstücke und werden verworfen. Alles andere bleibt in der Reihenfolge der Aufnahme erhalten.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from .align import norm


def find_extras(tr: list[dict], intervals: list[tuple[float, float, tuple[str, int]]], script_texts: list[str],
                pause: float = 1.2, min_words: int = 3, preroll: float = 0.15, postroll: float = 0.30,
                retake_score: float = 80.0) -> list[dict]:
    """`intervals`: [(in, out, (scene_id, block))] der abgeglichenen Blöcke dieser Aufnahme.

    Ergebnis (nach Zeit): [{in, out, text, after: (scene_id, block) | None, words}] – `after` ist der Block, der in der Aufnahme davor liegt.
    """
    ivs = sorted(intervals)
    outside = [w for w in tr if norm(w["w"]) and not any(a <= (w["start"] + w["end"]) / 2 <= b for a, b, _ in ivs)]
    runs: list[list[dict]] = []
    for w in outside:
        prev = runs[-1][-1] if runs else None
        crosses = prev is not None and any(prev["end"] <= a + 1e-6 and b <= w["start"] + 1e-6 for a, b, _ in ivs)
        if prev is None or w["start"] - prev["end"] > pause or crosses:
            runs.append([])
        runs[-1].append(w)
    scripts = [" ".join(norm(x) for x in t.split() if norm(x)) for t in script_texts if t.strip()]
    out = []
    for run in runs:
        text = " ".join(norm(w["w"]) for w in run)
        if len(run) < min_words:
            continue
        if any(fuzz.partial_ratio(text, s) >= retake_score for s in scripts):   # Wiederholung eines Skripttextes = Versprecher/Take
            continue
        t0, t1 = run[0]["start"], run[-1]["end"]
        prev_iv = [iv for iv in ivs if iv[1] <= t0 + 0.5]
        out.append({"in": round(max(0.0, t0 - preroll), 3), "out": round(t1 + postroll, 3),
                    "text": " ".join(w["w"] for w in run), "words": len(run),
                    "after": list(prev_iv[-1][2]) if prev_iv else None})
    return out
