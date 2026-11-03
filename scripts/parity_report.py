"""Paritätsbericht: Wie nah ist der Bridge-Schnitt am handgemachten Schnitt?

Aufruf:
  python scripts/parity_report.py <referenz.prproj> [--built <bridge.prproj>] [--plan <plan.json>] [--json]

Gemessen wird je Kategorie (Videoübergänge, Audioübergänge, Textclips, Bildcredits, Artwork-Sequenzen, Effekte, belegte Spuren).
Ohne --built/--plan wird nur die Referenz vermessen (das Soll). Mit --plan wird der Bauplan der Bridge gezählt (vor dem Bau in Premiere),
mit --built ein in Premiere gespeichertes, von der Bridge gebautes Projekt. Lücken werden unten aufgelistet.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from glorfindel.prproj_reader import Project  # noqa: E402

CATEGORIES = [
    ("video_uebergaenge", "Videoübergänge (Cross Dissolve)"),
    ("audio_uebergaenge", "Audioübergänge / Blenden"),
    ("textclips", "Editierbare Textclips"),
    ("bildcredits", "Credits als Bild (PNG)"),
    ("artwork_sequenzen", "Artwork als verschachtelte Sequenz"),
    ("einstellungsebenen", "Einstellungsebenen (Blur)"),
    ("effekte", "Effekt-Komponenten gesamt"),
    ("video_spuren", "Belegte Videospuren"),
    ("audio_spuren", "Belegte Audiospuren"),
]


def main_sequence(proj: Project):
    return max(proj.sequences(), key=lambda s: sum(len(v) for v in s.video.values()) + sum(len(v) for v in s.audio.values()))


def measure_project(path: str) -> dict:
    seq = main_sequence(Project.open(path))
    m = collections.Counter()
    for tracks, kind in ((seq.video, "video"), (seq.audio, "audio")):
        for items in tracks.values():
            if items:
                m[f"{kind}_spuren"] += 1
            for it in items:
                if it.kind == "unbekannt":                      # Übergänge erscheinen als Elemente ohne Namen
                    m[f"{kind}_uebergaenge"] += 1
                    continue
                m["effekte"] += len(it.comps)
                if it.kind == "grafik":
                    m["textclips"] += 1
                elif it.kind == "einstellungsebene":
                    m["einstellungsebenen"] += 1
                elif it.kind == "medium" and it.name.lower().endswith(".png") and kind == "video":
                    m["bildcredits"] += 1
                elif it.kind == "sequenz" and it.name.startswith("Verschachtelte Sequenz") and kind == "video":
                    m["artwork_sequenzen"] += 1
    return {"quelle": Path(path).name, "sequenz": seq.name, **{k: m[k] for k, _ in CATEGORIES}}


def measure_plan(path: str) -> dict:
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    m = collections.Counter()
    tracks_v, tracks_a = set(), set()
    for c in plan["clips"]:
        (tracks_a if c["kind"] == "voice" else tracks_v).add(c["track"])
        u = c.get("uebergang") or {}
        m["video_uebergaenge"] += sum(1 for k in ("ein", "aus") if u.get(k))
        b = c.get("ton_blende") or {}
        m["audio_uebergaenge"] += sum(1 for k in ("ein", "aus") if b.get(k))
        m["effekte"] += len(c.get("effects", []))
        if c["kind"] == "credit":
            m["textclips" if c.get("text_modus") == "mogrt" else "bildcredits"] += 1
        elif c["kind"] == "adjust":
            m["einstellungsebenen"] += 1
        elif c["kind"] == "artwork" and c.get("nested"):
            m["artwork_sequenzen"] += 1
    m["video_spuren"], m["audio_spuren"] = len(tracks_v), len(tracks_a) + (1 if any(c["kind"] == "episode" for c in plan["clips"]) else 0)
    return {"quelle": Path(path).name, "sequenz": plan["name"], **{k: m[k] for k, _ in CATEGORIES}}


def gaps(ref: dict, got: dict) -> list[str]:
    out = []
    for key, label in CATEGORIES:
        r, g = ref[key], got[key]
        if key.endswith("spuren"):
            continue                                            # Spurbelegung hängt vom Inhalt ab, nur anzeigen
        if r and g < 0.5 * r:
            out.append(f"{label}: {g} statt etwa {r} im Ursprungsschnitt")
        elif not r and g:
            out.append(f"{label}: {g} vorhanden, im Ursprungsschnitt keine")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("referenz")
    ap.add_argument("--built")
    ap.add_argument("--plan")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cols = [("Referenz", measure_project(a.referenz))]
    if a.plan:
        cols.append(("Plan", measure_plan(a.plan)))
    if a.built:
        cols.append(("Bridge", measure_project(a.built)))
    result = {"spalten": dict(cols), "luecken": {n: gaps(cols[0][1], c) for n, c in cols[1:]}}
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    print(f"{'':40}" + "".join(f"{n:>10}" for n, _ in cols))
    for key, label in CATEGORIES:
        print(f"{label:40}" + "".join(f"{c[key]:>10}" for _, c in cols))
    for n, lst in result["luecken"].items():
        print(f"\nLücken ({n}):" + ("" if lst else " keine"))
        for x in lst:
            print("  -", x)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
