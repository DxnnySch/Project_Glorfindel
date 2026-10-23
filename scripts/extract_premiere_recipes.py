"""Liest die Effekt-Rezepte (Artwork-Kette, Blur) aus einem fertigen Premiere-Projekt und schreibt vorlagen/premiere_rezepte.json.

Aufruf: python scripts/extract_premiere_recipes.py "F:\\OneDrive\\...\\Mythen - S2 E7_1.prproj" [Ausgabe.json]
Die Datei ist die Grundlage für den Rohschnitt in Premiere (Bridge): Effekte, Parameter und Keyframes stammen aus dem echten Schnitt.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from glorfindel.prproj_reader import Project, parse_value  # noqa: E402

FADE = 1 / 60  # Premiere setzt das letzte Keyframe ein Bild (60 fps) vor das Clipende


def param_entry(p, base: float = 0.0, clip_len: float | None = None) -> dict:
    e = {"index": p.index, "name": p.name, "value": parse_value(p.static)}
    if p.time_varying and p.keyframes:
        e["keyframes"] = [[round(t - base, 4), parse_value(v)] for t, v in p.keyframes]
    return e


def main(src: str, dst: str) -> None:
    proj = Project.open(src)
    main_seq = proj.sequence("MythenAusMittelerdeVideo")
    arts = [i for i in main_seq.video[2] + main_seq.video[3] if i.name.startswith("Verschachtelte Sequenz") and len(i.comps) >= 4]
    art = arts[1]
    dur = art.end - art.start
    chain = []
    for c in art.comps:
        entry = {"match_name": c.match_name, "display": c.display, "params": []}
        if c.match_name == "AE.ADBE Roughen Edges":
            first_t = min(t for p in c.params if p.time_varying and p.keyframes for t, _ in p.keyframes)
            is_out = first_t > dur / 2
            entry["id"] = "fancy_out" if is_out else "fancy_in"
            entry["anchor"] = "end" if is_out else "start"
            entry["color_param"] = "Konturfarbe"
            base = dur if is_out else 0.0
            entry["params"] = [param_entry(p, base) for p in c.params if p.name.strip()]
        else:
            entry["id"] = {"AE.ADBE Drop Shadow": "drop_shadow", "AE.ADBE Geometry": "zoom"}.get(c.match_name, c.match_name)
            entry["anchor"] = "start"
            entry["params"] = [param_entry(p) for p in c.params if p.name.strip()]
        chain.append(entry)
    # Gegenprobe: alle Fancy-Out-Keyframes liegen bei allen Artworks gleich weit vom Ende entfernt
    offs = []
    for a in arts[:12]:
        d = a.end - a.start
        for c in a.comps:
            for p in c.params:
                if p.name == "Rahmen" and p.keyframes and min(t for t, _ in p.keyframes) > d / 2:
                    offs.append(round(p.keyframes[0][0] - d, 3))
    # Blur: Einstellungsebenen mit Gaußschem Weichzeichner (Zeitbasis der Einstellungsebene: 1 h Versatz)
    blur_in = blur_out = None
    for it in main_seq.video[1]:
        if it.kind == "einstellungsebene":
            for c in it.comps:
                if c.match_name == "AE.ADBE Gaussian Blur 2":
                    p = next(q for q in c.params if q.index == 0)
                    if p.time_varying and p.keyframes:
                        t0 = p.keyframes[0][0]
                        kfs = [[round(t - t0, 4), parse_value(v)] for t, v in p.keyframes]
                        if len(kfs) == 2 and blur_in is None:
                            blur_in = {"match_name": c.match_name, "param_index": 0, "param": p.name, "keyframes": kfs}
                        if len(kfs) == 4 and blur_out is None:
                            d = it.end - it.start
                            blur_out = {"match_name": c.match_name, "param_index": 0, "param": p.name,
                                        "keyframes": [[kfs[0][0], kfs[0][1]], [kfs[1][0], kfs[1][1]], [round(kfs[2][0] - d, 4), kfs[2][1]], [round(kfs[3][0] - d, 4), kfs[3][1]]],
                                        "anchor_end_from": 2}
    out = {"schema": 1, "quelle": Path(src).name,
           "hinweis": "Zeiten in Sekunden. anchor=start: ab Clipanfang; anchor=end: relativ zum Clipende (negativ). Farben als argb16 [a,r,g,b].",
           "artwork_kette": chain, "fancy_out_offsets_gemessen": sorted(set(offs)),
           "blur": {"ein": blur_in, "ein_aus": blur_out, "match_name": "AE.ADBE Gaussian Blur 2"},
           "tracks_original": {f"V{k + 1}": len(v) for k, v in main_seq.video.items() if v}}
    Path(dst).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("geschrieben:", dst, "| Komponenten:", [c["id"] for c in chain], "| Out-Versatz:", out["fancy_out_offsets_gemessen"])


if __name__ == "__main__":
    default_dst = Path(__file__).resolve().parents[1] / "vorlagen" / "premiere_rezepte.json"
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else str(default_dst))
