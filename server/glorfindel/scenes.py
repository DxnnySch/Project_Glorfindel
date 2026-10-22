"""Szenen: Längenampel, Sprechdauer, Sortierung nach Strängen (Heft §5.2/5.3)."""
from __future__ import annotations

import re
from typing import Literal

from .config import Thresholds
from .models import CommentBlock, Scene, Strand

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


_BULLET_RE = re.compile(r"^\s*(?:[-–—•*·]|\d+[.)])\s+")


def parse_bullets(text: str) -> list[str]:
    """Zeilen mit Aufzählungszeichen -> Stichpunkte; leer, wenn der Text kein Stichpunkt-Skript ist."""
    lines = [l for l in text.splitlines() if l.strip()]
    if lines and all(_BULLET_RE.match(l) for l in lines):
        return [_BULLET_RE.sub("", l).strip() for l in lines]
    return []


def normalize_block(block: CommentBlock) -> CommentBlock:
    """Erkennt Stichpunkt-Eingaben im Textfeld und stellt Modus/Felder konsistent her."""
    if block.modus == "text":
        bullets = parse_bullets(block.text)
        if bullets:
            block.modus, block.stichpunkte, block.text = "stichpunkte", bullets, ""
    elif block.modus == "stichpunkte" and block.text and not block.stichpunkte:
        block.stichpunkte, block.text = parse_bullets(block.text) or [block.text], ""
    return block


def block_duration(block: CommentBlock, th: Thresholds) -> float:
    if block.modus == "stichpunkte":
        return len(block.stichpunkte) * th.bullet_seconds
    return speech_duration(block.text, th)


def scene_report(scene: Scene, th: Thresholds) -> dict:
    segs = [{"duration": s.duration, "light": segment_light(s.duration, th)} for s in scene.segmente]
    order = {"gruen": 0, "gelb": 1, "rot": 2}
    worst: Light = max((s["light"] for s in segs), key=order.get, default="grau")  # type: ignore[arg-type]
    return {
        "id": scene.id,
        "segments": segs,
        "light": worst,
        "series_s": scene_series_duration(scene),
        "comment_s": sum(block_duration(c, th) for c in scene.kommentar),
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


def validate_segments(scene: Scene, max_t: float = 0.0) -> list[str]:
    """Plausibilitätsprüfung; leere Liste = in Ordnung."""
    problems = []
    for i, s in enumerate(scene.segmente):
        if s.out <= s.in_:
            problems.append(f"Segment {i + 1}: Out liegt nicht nach In")
        if max_t and s.out > max_t + 0.5:
            problems.append(f"Segment {i + 1}: liegt hinter dem Ende der Episode ({max_t:.0f} s)")
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
