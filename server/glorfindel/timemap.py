"""Zeitabbildung Episodenzeit <-> Quellzeit über Ankerpunkte (Heft §4).

Ein Anker: reiner Versatz (a=1). Zwei oder mehr: stückweise linear zwischen den Ankern,
außerhalb mit dem Verhalten des ersten/letzten Intervalls fortgesetzt.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from .models import Anchor


@dataclass(frozen=True)
class Piece:
    ref0: float
    ref1: float       # inf für das letzte Stück
    a: float
    b: float          # t_src = a*t_ref + b

    def apply(self, t: float) -> float:
        return self.a * t + self.b


class TimeMap:
    def __init__(self, anchors: list[Anchor] | list[tuple[float, float]] | None = None):
        pts = sorted(((a.ref, a.src) if isinstance(a, Anchor) else tuple(a)) for a in (anchors or []))
        # doppelte ref-Werte würden Division durch 0 erzeugen
        dedup: list[tuple[float, float]] = []
        for r, s in pts:
            if dedup and abs(dedup[-1][0] - r) < 1e-9:
                dedup[-1] = (r, s)
            else:
                dedup.append((r, s))
        self.points = dedup
        self.pieces = self._build()

    def _build(self) -> list[Piece]:
        p = self.points
        if not p:
            return [Piece(float("-inf"), float("inf"), 1.0, 0.0)]
        if len(p) == 1:
            r, s = p[0]
            return [Piece(float("-inf"), float("inf"), 1.0, s - r)]
        pieces = []
        for i in range(len(p) - 1):
            (r0, s0), (r1, s1) = p[i], p[i + 1]
            a = (s1 - s0) / (r1 - r0)
            b = s0 - a * r0
            lo = float("-inf") if i == 0 else r0
            hi = float("inf") if i == len(p) - 2 else r1
            pieces.append(Piece(lo, hi, a, b))
        return pieces

    def pure_offset(self) -> float | None:
        """Reine Verschiebung (HQ-Zeit = Referenzzeit + Offset, gleiche Geschwindigkeit)? Dann Offset, sonst None."""
        if all(abs(pc.a - 1.0) < 1e-6 for pc in self.pieces) and max(pc.b for pc in self.pieces) - min(pc.b for pc in self.pieces) < 1e-3:
            return self.pieces[0].b
        return None

    @property
    def is_identity(self) -> bool:
        return all(abs(pc.a - 1) < 1e-12 and abs(pc.b) < 1e-9 for pc in self.pieces)

    def _piece(self, t: float) -> Piece:
        starts = [pc.ref0 for pc in self.pieces]
        i = max(0, bisect_right(starts, t) - 1)
        return self.pieces[i]

    def ref_to_src(self, t: float) -> float:
        return self._piece(t).apply(t)

    def src_to_ref(self, s: float) -> float:
        """Inverse; bei streng monotoner Abbildung eindeutig."""
        for pc in self.pieces:
            lo, hi = pc.apply(max(pc.ref0, -1e12)), pc.apply(min(pc.ref1, 1e12))
            if min(lo, hi) - 1e-9 <= s <= max(lo, hi) + 1e-9:
                return (s - pc.b) / pc.a
        pc = self.pieces[-1] if s > 0 else self.pieces[0]
        return (s - pc.b) / pc.a

    def pieces_over(self, ref_start: float, ref_end: float) -> list[Piece]:
        """Stücke, die das Intervall [ref_start, ref_end] berühren (für Conform)."""
        return [pc for pc in self.pieces if pc.ref1 > ref_start and pc.ref0 < ref_end]

    def to_json(self) -> list[dict]:
        return [{"ref": r, "src": s} for r, s in self.points]
