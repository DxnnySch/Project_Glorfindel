"""Abgleich Premiere → App: Wurden Serienclips in Premiere gekürzt, verlängert oder geteilt, übernimmt die App die neuen
Ein-/Aus-Punkte in die Segmente der Szenen. Daraus ergibt sich, welche Standbilder in Premiere ersetzt werden müssen."""
from __future__ import annotations

import re

from . import rough_cut
from .models import Scene, Segment

NAME_RE = re.compile(r"^(\S+) Segment(?: (\d+))?$")        # „sz_06 Segment 2“ (ältere Bauten: ohne Nummer)
MIN_PIECE_S = 0.1


def pieces_from_dump(dump: dict, off: float = 0.0) -> dict[str, dict[int, list[dict]]]:
    """Serienclips der Sequenz je Szene und Segmentnummer (1-basiert). `in`/`out` in Episodenzeit (ohne Offset der Referenz)."""
    out: dict[str, dict[int, list[dict]]] = {}
    for tr in dump.get("tracks", []):
        if not str(tr.get("track", "")).startswith("V"):
            continue
        unnumbered: dict[str, int] = {}
        for it in sorted(tr.get("items", []), key=lambda i: i.get("start", 0)):
            m = NAME_RE.match(it.get("name") or "")
            if not m or it["out"] - it["in"] < MIN_PIECE_S:
                continue
            sid = m.group(1)
            if m.group(2):
                num = int(m.group(2))
            else:
                unnumbered[sid] = num = unnumbered.get(sid, 0) + 1
            out.setdefault(sid, {}).setdefault(num, []).append({"start": it["start"], "in": it["in"] - off, "out": it["out"] - off})
    return out


def _ranges(pieces: list[dict], tol: float) -> list[tuple[float, float]]:
    """Zeitlich aufeinanderfolgende Stücke, die in der Quelle nahtlos anschließen (Schnitt ohne Lücke), werden wieder ein Bereich."""
    rs: list[list[float]] = []
    for p in sorted(pieces, key=lambda p: p["start"]):
        if rs and abs(p["in"] - rs[-1][1]) <= tol:
            rs[-1][1] = p["out"]
        else:
            rs.append([p["in"], p["out"]])
    return [(a, b) for a, b in rs]


def compare(scenes: list[Scene], pieces: dict[str, dict[int, list[dict]]], fps: float = rough_cut.EPISODE_FPS) -> list[dict]:
    """Unterschiede zwischen den Segmenten der App und den Clips in Premiere.
    typ: „geaendert“ (neue Ein-/Aus-Punkte), „geteilt“ (mehrere getrennte Bereiche), „entfernt“ (Clip fehlt; wird nur gemeldet)."""
    tol = 0.5 / fps
    out = []
    for sc in scenes:
        got = pieces.get(sc.id)
        if not got:
            continue                                                # Szene nicht im Rohschnitt (oder anders benannt): nichts ableiten
        for i, seg in enumerate(sc.segmente):
            ps = got.get(i + 1)
            base = {"scene": sc.id, "titel": sc.titel or sc.id, "index": i, "alt": [round(seg.in_, 3), round(seg.out, 3)]}
            if not ps:
                out.append({**base, "typ": "entfernt", "neu": []})
                continue
            rs = _ranges(ps, tol)
            snapped = [(rough_cut.snap_ep(a, fps), rough_cut.snap_ep(b, fps)) for a, b in rs]
            if len(rs) == 1:
                a, b = snapped[0]
                if abs(a - seg.in_) > tol or abs(b - seg.out) > tol:
                    out.append({**base, "typ": "geaendert", "neu": [[round(a, 3), round(b, 3)]]})
            else:
                out.append({**base, "typ": "geteilt", "neu": [[round(a, 3), round(b, 3)] for a, b in snapped]})
    return out


def apply(scenes: list[Scene], changes: list[dict]) -> list[Scene]:
    """Übernimmt „geaendert“ und „geteilt“ in die Szenen (Kopien werden direkt verändert). Rückgabe: die geänderten Szenen.
    Beim Teilen behält der erste Teil die Notiz; Kommentare des Segments hängen am letzten Teil, spätere Segmente rücken nach."""
    by_scene: dict[str, list[dict]] = {}
    for c in changes:
        if c["typ"] in ("geaendert", "geteilt"):
            by_scene.setdefault(c["scene"], []).append(c)
    touched = []
    for sc in scenes:
        cs = {c["index"]: c for c in by_scene.get(sc.id, [])}
        if not cs:
            continue
        new_segs: list[Segment] = []
        last_of: dict[int, int] = {}
        for i, seg in enumerate(sc.segmente):
            c = cs.get(i)
            if not c:
                new_segs.append(seg)
            else:
                for k, (a, b) in enumerate(c["neu"]):
                    new_segs.append(Segment(**{"in": a, "out": b, "notiz": seg.notiz if k == 0 else ""}))
            last_of[i] = len(new_segs) - 1
        for block in sc.kommentar:
            if block.segment is not None and block.segment in last_of:
                block.segment = last_of[block.segment]
        sc.segmente = new_segs
        touched.append(sc)
    return touched


def stale_stills(new_times: dict[str, float], built_times: dict[str, float], tol: float = 0.02) -> dict:
    """Welche Standbilder in Premiere nicht mehr zum Modell passen. `neu`/`gebaut`: Dateiname → Zeit in der Referenz.
    `struktur`: andere Standbilder als beim Bau (Anzahl/Namen) – das lässt sich nicht tauschen, nur neu bauen."""
    stale = {n: t for n, t in new_times.items() if n in built_times and abs(t - built_times[n]) > tol}
    return {"tausch": stale, "struktur": set(new_times) != set(built_times)}
