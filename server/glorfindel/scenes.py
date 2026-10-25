"""Szenen: Längenampel, Sprechdauer, Sortierung nach Strängen (Heft §5.2/5.3)."""
from __future__ import annotations

import re
from typing import Literal

from .config import Thresholds
from . import richtext
from .models import CommentBlock, Scene, Strand

Light = Literal["gruen", "gelb", "rot"]


def segment_light(duration: float, th: Thresholds) -> Light:
    if duration > th.max_segment_s:
        return "rot"
    if duration > th.max_segment_s * th.warn_ratio:
        return "gelb"
    return "gruen"


def segment_of(block: CommentBlock, scene: Scene) -> int:
    """Index des Segments, zu dem ein Kommentarblock gehört (Standard: letztes Segment, ohne Segmente 0)."""
    n = len(scene.segmente)
    if n == 0:
        return 0
    return block.segment if block.segment is not None and 0 <= block.segment < n else n - 1


def still_plan(scene: Scene) -> list[int]:
    """Segmente, nach denen ein Standbild folgt: alle mit Kommentar plus das letzte Segment (wenn Standbild nicht „aus“)."""
    if scene.standbild == "aus" or not scene.segmente:
        return []
    with_comment = {segment_of(b, scene) for b in scene.kommentar}
    return sorted(with_comment | {len(scene.segmente) - 1})


def in_video(scene: Scene) -> bool:
    """Eine Szene ist nur Messeinheit. Ins Video (und ins Skript) kommen nur Segmente – Szenen ohne Segment und
    ohne Kommentar kommen nicht vor."""
    return bool(scene.segmente or scene.kommentar)


MIN_OVERLAP_S = 0.3   # so viel muss ein Segment in eine Szene hineinreichen, damit sie als „berührt“ gilt


def unit_numbers(scenes: list[Scene]) -> dict[str, int]:
    """Zeitliche Nummer der Szenen (Messeinheiten) 1..N nach Beginn ihres Bereichs."""
    units = sorted((s for s in scenes if s.bereich), key=lambda s: (s.bereich[0], s.id))
    return {s.id: i + 1 for i, s in enumerate(units)}


def coverage(scenes: list[Scene]) -> dict:
    """Welche Szenen (Messeinheiten) überdeckt welches Segment? Ein Segment kann eine Szene sein, mehrere Szenen
    überspannen oder nur einen Teil einer Szene ausmachen – unabhängig davon, in welcher Szene es angelegt wurde.

    Rückgabe: {'nr': {szene: nummer}, 'segments': {szene: [ {'szenen': [ids], 'nr': [nummern], 'anteil': {id: 0..1}} ]},
               'touched': {szene: [ {'scene': heimat, 'index': i, 'in': a, 'out': b} ]}}"""
    nr = unit_numbers(scenes)
    units = sorted((s for s in scenes if s.bereich), key=lambda s: s.bereich[0])
    seg_info: dict[str, list[dict]] = {}
    touched: dict[str, list[dict]] = {u.id: [] for u in units}
    for sc in scenes:
        rows = []
        for i, g in enumerate(sc.segmente):
            hit, share = [], {}
            for u in units:
                a, b = max(g.in_, u.bereich[0]), min(g.out, u.bereich[1])
                if b - a >= MIN_OVERLAP_S:
                    hit.append(u.id)
                    share[u.id] = round((b - a) / max(1e-6, u.bereich[1] - u.bereich[0]), 3)
                    touched[u.id].append({"scene": sc.id, "index": i, "in": g.in_, "out": g.out})
            rows.append({"szenen": hit, "nr": [nr[x] for x in hit], "anteil": share})
        seg_info[sc.id] = rows
    return {"nr": nr, "segments": seg_info, "touched": touched}


def overlap_problems(scenes: list[Scene]) -> dict[str, list[str]]:
    """Segmente verschiedener (oder derselben) Szene, die sich zeitlich überschneiden: dieselbe Stelle käme doppelt ins Video."""
    segs = [(sc, i, g) for sc in scenes for i, g in enumerate(sc.segmente)]
    out: dict[str, list[str]] = {}
    for x in range(len(segs)):
        for y in range(x + 1, len(segs)):
            (sa, ia, ga), (sb, ib, gb) = segs[x], segs[y]
            ov = min(ga.out, gb.out) - max(ga.in_, gb.in_)
            if ov > 0.25:
                lab_b = f"Segment {ib + 1}" + ("" if sa.id == sb.id else f" von „{sb.titel or sb.id}“")
                lab_a = f"Segment {ia + 1}" + ("" if sa.id == sb.id else f" von „{sa.titel or sa.id}“")
                out.setdefault(sa.id, []).append(f"Segment {ia + 1} überschneidet sich {ov:.1f} s mit {lab_b}")
                if sb.id != sa.id:
                    out.setdefault(sb.id, []).append(f"Segment {ib + 1} überschneidet sich {ov:.1f} s mit {lab_a}")
    return out


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
    if block.markup:
        if block.modus == "text" and richtext.has_markup(block.markup):
            block.text = richtext.plain(block.markup)           # Formatierung gewinnt; Aufzählungen bleiben Fließtext
            return block
        block.markup = ""
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


def apply_ablauf(sorted_scenes: list[Scene], ablauf: list[str]) -> list[Scene]:
    """Manuelle Reihenfolge anwenden; unbekannte/neue Szenen behalten ihre automatische Position hinten."""
    if not ablauf:
        return sorted_scenes
    by_id = {s.id: s for s in sorted_scenes}
    first = [by_id[i] for i in ablauf if i in by_id]
    rest = [s for s in sorted_scenes if s.id not in set(ablauf)]
    return first + rest


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
