"""Szenen: Längenampel, Sprechdauer, Sortierung nach Strängen (Heft §5.2/5.3)."""
from __future__ import annotations

import re
from typing import Literal

from .config import Thresholds
from .models import Scene, Strand

Light = Literal["gruen", "gelb", "rot"]


def segment_light(duration: float, th: Thresholds) -> Light:
    if duration > th.max_segment_s:
        return "rot"
    if duration > th.max_segment_s * th.warn_ratio:
        return "gelb"
    return "gruen"


def scene_series_duration(scene: Scene) -> float:
    return sum(s.duration for s in scene.segmente)


def count_words(text: str) -> int:
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def speech_duration(text: str, th: Thresholds) -> float:
    return count_words(text) / th.words_per_second


def scene_report(scene: Scene, th: Thresholds) -> dict:
    segs = [{"duration": s.duration, "light": segment_light(s.duration, th)} for s in scene.segmente]
    order = {"gruen": 0, "gelb": 1, "rot": 2}
    worst: Light = max((s["light"] for s in segs), key=order.get, default="gruen")
    return {
        "id": scene.id,
        "segments": segs,
        "light": worst,
        "series_s": scene_series_duration(scene),
        "comment_s": sum(speech_duration(c.text, th) for c in scene.kommentar),
        "montage": len(scene.segmente) > 1,
    }


def episode_report(scenes: list[Scene], th: Thresholds) -> dict:
    reps = [scene_report(s, th) for s in scenes]
    series = sum(r["series_s"] for r in reps)
    comment = sum(r["comment_s"] for r in reps)
    total = series + comment
    share = series / total if total else 0.0
    return {
        "scenes": reps,
        "series_s": series,
        "comment_s": comment,
        "total_s": total,
        "series_share": share,
        "share_light": "gruen" if share <= th.target_series_share else "rot",
    }


def validate_segments(scene: Scene) -> list[str]:
    """Plausibilitätsprüfung; leere Liste = in Ordnung."""
    problems = []
    for i, s in enumerate(scene.segmente):
        if s.out <= s.in_:
            problems.append(f"Segment {i + 1}: Out liegt nicht nach In")
        if s.in_ < 0:
            problems.append(f"Segment {i + 1}: negative Zeit")
    return problems


def sort_scenes(scenes: list[Scene], strands: list[Strand]) -> list[Scene]:
    """Szenen nach Strang-Reihenfolge, innerhalb eines Strangs nach `reihenfolge`.

    Fixierte Szenen („dramaturgisch fixieren“) behalten ihre globale Position
    (Index nach `reihenfolge` über die Eingabeliste), alle anderen füllen die Lücken.
    """
    rank = {s.id: s.order for s in strands}
    base = sorted(scenes, key=lambda s: (s.reihenfolge, s.id))
    fixed = {i: sc for i, sc in enumerate(base) if sc.fixiert}
    movable = sorted(
        (sc for sc in base if not sc.fixiert),
        key=lambda s: (rank.get(s.strang, 10_000), s.reihenfolge, s.id),
    )
    out: list[Scene] = []
    it = iter(movable)
    for i in range(len(base)):
        out.append(fixed[i] if i in fixed else next(it))
    return out
