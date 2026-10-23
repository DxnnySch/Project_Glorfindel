"""Szenen sind Messeinheiten, Segmente das, was ins Video kommt.

Ältere Projekte haben beim Board-Anlegen für jede erkannte Szene automatisch ein 9,5-s-Segment bekommen und keinen
Szenenbereich gespeichert. Diese einmalige Umstellung
  * trägt den Bereich (Start/Ende) aus den Board-Vorschlägen nach und
  * entfernt die automatisch erzeugten, unbearbeiteten Segmente (ohne Notiz, ohne Kommentar, Länge = Standard).
Eigene Segmente, Kommentare und Notizen bleiben unberührt. Vorher wird jede geänderte Szene gesichert.
"""
from __future__ import annotations

import re

from . import store
from .scenes import segment_of
from .service import Episode

AUTO_SEGMENT_S = 9.5
TOL = 0.12


def _title_time(titel: str) -> float | None:
    m = re.search(r"ab\s+(?:(\d+):)?(\d+):(\d+)(?:[.,](\d+))?", titel or "")
    if not m:
        return None
    h, mi, se, fr = int(m[1] or 0), int(m[2]), int(m[3]), m[4]
    return h * 3600 + mi * 60 + se + (int(fr) / 10 ** len(fr) if fr else 0.0)


def _proposal_for(scene, proposals: list[dict]) -> dict | None:
    candidates = []
    if scene.segmente:
        candidates.append(scene.segmente[0].in_)
    t = _title_time(scene.titel)
    if t is not None:
        candidates.append(t)
    for c in candidates:
        best = min(proposals, key=lambda p: abs(p["start"] - c), default=None)
        if best is not None and abs(best["start"] - c) <= TOL:
            return best
    return None


def migrate(ep: Episode) -> dict:
    """Einmalig und idempotent. Gibt eine kurze Bilanz zurück."""
    pr = ep.project()
    if pr.einheiten_migriert:
        return {"done": False, "reason": "bereits umgestellt"}
    scenes = ep.scenes()
    todo = [s for s in scenes if not s.bereich]
    board = store.read_json(ep.p.cache() / "board.json", None)
    proposals = [p for p in (board or {}).get("scenes", []) if "start" in p and "end" in p]
    if todo and not proposals:
        return {"done": False, "reason": "keine Szenenerkennung auf diesem Rechner (Board)"}  # später erneut versuchen
    ranged = dropped = 0
    backup = ep.p.gl / "sicherung"
    for sc in todo:
        prop = _proposal_for(sc, proposals)
        if prop is None:
            continue
        before = sc.model_dump(by_alias=True)
        sc.bereich = [round(prop["start"], 3), round(prop["end"], 3)]
        ranged += 1
        keep, remap = [], {}
        for i, g in enumerate(sc.segmente):
            auto = (abs(g.in_ - prop["start"]) <= TOL and abs(g.out - min(prop["end"], prop["start"] + AUTO_SEGMENT_S)) <= TOL
                    and not (g.notiz or "").strip() and not any(segment_of(b, sc) == i for b in sc.kommentar))
            if auto:
                dropped += 1
            else:
                remap[i] = len(keep)
                keep.append(g)
        if len(keep) != len(sc.segmente):
            for b in sc.kommentar:
                if b.segment is not None:
                    b.segment = remap.get(b.segment)
                    # (Kommentare ohne Segmentangabe gehören ohnehin zum letzten Segment: bleibt so)
            sc.segmente = keep
        store.write_json(backup / f"{sc.id}_vor_einheiten.json", before)
        ep.save_scene(sc, f"Szene {sc.id}: Messeinheit (Bereich {sc.bereich[0]:.1f}–{sc.bereich[1]:.1f} s), automatisches Segment entfernt")
    still_open = [s for s in ep.scenes() if not s.bereich]
    if not still_open or ranged:
        pr = ep.project()
        pr.einheiten_migriert = True
        ep.save_project(pr)
    store.log_change(ep.p.gl, ep.settings.user, f"Szenen als Messeinheiten umgestellt: {ranged} Bereiche, {dropped} automatische Segmente entfernt")
    return {"done": True, "bereiche": ranged, "segmente_entfernt": dropped, "ohne_bereich": len(still_open)}
