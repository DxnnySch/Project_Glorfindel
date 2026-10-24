"""Bauplan für Premiere: macht aus dem Schnittpaket (`schnitt_vN.json`) eine deklarative Liste von Medien und Clips.

Der Plan ist reine Daten (JSON) – das Panel in Premiere führt ihn aus. Alle Zeiten in Sekunden, Spurindizes 0-basiert
(V1 = 0). Effekte sind vollständig aufgelöst (Parameter, Keyframes in Clip-Zeit), damit das Panel nichts interpretieren muss.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

SCHEMA = 1
DEFAULT_RECIPES = Path(__file__).resolve().parents[2] / "vorlagen" / "premiere_rezepte.json"


def load_recipes(path: Path | None = None) -> dict:
    p = path if path and path.exists() else DEFAULT_RECIPES
    return json.loads(p.read_text(encoding="utf-8"))


def track_index(name: str) -> tuple[str, int]:
    """'V10' -> ('video', 9), 'A4' -> ('audio', 3)"""
    kind = "video" if name[0].upper() == "V" else "audio"
    return kind, int(name[1:]) - 1


def hex_to_argb16(color: str) -> list[int]:
    """'#d45329' -> [a, r, g, b] mit je 16 Bit (Premiere speichert 8 Bit als Wert << 8)."""
    c = color.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return [0xFF00, r << 8, g << 8, b << 8]


@dataclass
class PlanEnv:
    root: Path                                   # OneDrive-Stamm
    episode_media: Path                          # konforme Referenz (liegt in der Episoden-Sequenz)
    stills_dir: Path                             # Ordner „Videoelemente“
    credit: Callable[[str, str, float | None], Path]           # (text, art, x_mitte) -> PNG
    image_size: Callable[[Path], tuple[int, int] | None]       # Pixelgröße eines Bildes/Videos
    recipes: dict = field(default_factory=dict)
    premiere: dict = field(default_factory=dict)              # Einstellungen: aep, comp, play_in, pause_in, preset (Pfad .sqpreset), tracks
    doppel: dict = field(default_factory=dict)                # Positionen für Doppelbild-Layouts


def _resolve_chain(recipes: dict, ids: list[dict], dur: float, contour: str | None, fps: float) -> list[dict]:
    """Rezept-Komponenten eines Clips auflösen: Farbe einsetzen, Keyframes auf Clip-Zeit (Sekunden ab Clipanfang) bringen."""
    out = []
    by_id = {c["id"]: c for c in recipes.get("artwork_kette", [])}
    for ref in ids:
        c = by_id.get(ref["recipe"])
        if c is None:
            continue
        params = []
        for p in c["params"]:
            e = {"index": p["index"], "name": p["name"], "value": p["value"]}
            if c.get("color_param") == p["name"] and contour:
                e["value"] = {"argb16": hex_to_argb16(contour)}
            if p.get("keyframes"):
                kfs = []
                for t, v in p["keyframes"]:
                    ta = dur + t if c["anchor"] == "end" else t
                    if 0 <= ta <= max(dur, 0) + 1e-6 or c["id"] == "zoom":
                        kfs.append([round(max(ta, 0.0), 4), v])
                if kfs:
                    e["keyframes"] = kfs
            params.append(e)
        out.append({"id": c["id"], "match_name": c["match_name"], "display": c.get("display", ""), "params": params})
    return out


def _square_crop(w: int, h: int) -> dict:
    """Mittiges Quadrat aus einem Bild w×h als Zuschneiden-Prozente."""
    if w >= h:
        side = (w - h) / 2 / w * 100
        return {"links": side, "rechts": side, "oben": 0.0, "unten": 0.0}
    side = (h - w) / 2 / h * 100
    return {"links": 0.0, "rechts": 0.0, "oben": side, "unten": side}


def build_plan(pkg: dict, env: PlanEnv) -> dict:
    warnings: list[str] = list(pkg.get("warnings", []))
    media: dict[str, dict] = {}
    by_path: dict[str, str] = {}

    def reg(path: Path, kind: str, **extra) -> str:
        key = str(path)
        if key not in by_path:
            mid = f"m{len(media) + 1}"
            by_path[key] = mid
            media[mid] = {"id": mid, "path": key, "kind": kind, **extra}
        return by_path[key]

    ep_id = reg(env.episode_media, "episode")
    clips: list[dict] = []
    blur_periods: list[tuple[float, float]] = []
    fps = pkg["sequence"]["fps"]
    recipes = env.recipes
    snap = lambda t: round(t * fps) / fps  # noqa: E731 – Raster der Hauptsequenz (60 fps): keine Teilbild-Überlappungen

    def abs_path(rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else env.root / rel

    for tname, items in pkg["tracks"].items():
        if tname == "GAP":
            continue
        kind_t, idx = track_index(tname)
        for c in sorted(items, key=lambda c: c["start"]):
            typ, start, end = c["type"], c["start"], c["end"]
            start, end = snap(start), snap(end)
            dur = end - start
            base = {"start": start, "end": end, "track": idx, "scene": c.get("scene", "")}
            if typ == "scene_segment":
                clips.append({"kind": "episode", **base, "media": ep_id, "src_in": c["src_in"], "src_out": c["src_out"],
                              "audio": 3, "name": f"{c.get('scene', '')} Segment"})
            elif typ == "scene_audio":
                continue                                            # Ton hängt am verknüpften Episoden-Clip (A4)
            elif typ == "still":
                if not c.get("file"):
                    warnings.append(f"{c.get('scene', '')}: Standbild ohne Datei – Lücke bleibt")
                    continue
                f = env.stills_dir / Path(c["file"]).name
                clips.append({"kind": "still", **base, "media": reg(f, "still"), "name": f.stem})
            elif typ == "anim":
                pr = env.premiere
                clips.append({"kind": "anim", **base, "template": c["name"], "name": c["name"], "comp": pr.get("comp", "Play-Pause"),
                              "comp_in": float(pr.get("pause_in", 28.7) if c["name"] == "Pause" else pr.get("play_in", 0.0))})
            elif typ == "blur":
                blur_periods.append((start, end))                   # wird unten dem Standbild als Effekt zugeordnet
            elif typ == "artwork":
                f = abs_path(c["file"]) if c.get("file") else None
                if f is None or not f.exists():
                    warnings.append(f"{c.get('scene', '')}: Artwork {c.get('ref')} nicht gefunden ({f}) – übersprungen")
                    continue
                size = env.image_size(f) or (1920, 1080)
                contour = next((e.get("contour") for e in c.get("effects", []) if e["recipe"] == "fancy_in"), None)
                lay = c.get("layout", "einzel")
                pos = env.doppel.get("links" if lay == "doppel_links" else "rechts") if lay != "einzel" else None
                target_px = (pos["size"] * 1080) if pos else 1000.0
                clip = {"kind": "artwork", **base, "media": reg(f, "artwork", size=list(size)), "name": f.stem,
                        "crop": _square_crop(*size), "scale": round(target_px / min(size) * 100, 3),
                        "position": [pos["x"], pos["y"]] if pos else [0.5, 0.5],
                        "effects": _resolve_chain(recipes, [{"recipe": r} for r in ("drop_shadow", "zoom", "fancy_out", "fancy_in")], dur, contour, fps)}
                clips.append(clip)
            elif typ == "credit":
                art = {"credit_amazon": "amazon", "credit_artwork": "artwork", "credit_musik": "musik"}.get(c.get("slot", ""), "artwork")
                x = env.doppel.get("links" if c.get("layout") == "doppel_links" else "rechts", {}).get("x")                     if art == "artwork" and c.get("layout") in ("doppel_links", "doppel_rechts") else None
                png = env.credit(c["text"], art, x)
                clips.append({"kind": "credit", **base, "media": reg(png, "credit"), "name": c["text"],
                              "fade": c.get("fade", 0.0) or 0.0})
            elif typ == "comment":
                if c.get("placeholder") or not c.get("rec_path"):
                    continue                                        # noch keine Aufnahme: Marker genügt (siehe Warnungen)
                f = abs_path(c["rec_path"])
                clips.append({"kind": "voice", **base, "media": reg(f, "voice"), "src_in": c["src_in"], "src_out": c["src_out"],
                              "name": f"{c.get('speaker', '')} {c.get('scene', '')}"})
            elif typ == "map_placeholder":
                f = abs_path(c["file"]) if c.get("file") else None
                if f is None or not f.exists():
                    warnings.append(f"{c.get('scene', '')}: Kartenplatzhalter {c.get('ref')} noch nicht gerendert – nur Marker")
                    continue
                clips.append({"kind": "map", **base, "media": reg(f, "map"), "name": c.get("ref", "Karte")})
    _assign_blur(clips, merge_periods(blur_periods), recipes, warnings)
    # Videospuren zuerst, je Spur nach Zeit; Premiere bekommt feste Reihenfolge für deterministische Ergebnisse
    clips.sort(key=lambda c: (0 if c["kind"] != "voice" else 1, c["track"], c["start"]))
    return {
        "schema": SCHEMA, "name": pkg["sequence"]["name"], "slug": pkg.get("slug", ""), "fps": fps,
        "episode_sequence": pkg["episode_sequence"], "bin": f"Glorfindel {pkg['sequence']['name']}",
        "anim_source": {"aep": env.premiere.get("aep", ""), "comp": env.premiere.get("comp", "Play-Pause")},
        "preset": {"path": env.premiere.get("preset", ""), "video_tracks": env.premiere.get("video_tracks", 14),
                   "audio_tracks": env.premiere.get("audio_tracks", 16)},
        "media": list(media.values()), "clips": clips,
        "markers": [{"time": snap(m["time"]), "name": m["text"][:60], "comment": m["text"], "kind": m.get("kind", "")} for m in pkg.get("markers", [])],
        "warnings": warnings,
        "stats": {"clips": len(clips), "media": len(media), "duration": pkg.get("duration", 0.0),
                  "by_kind": {k: sum(1 for c in clips if c["kind"] == k) for k in sorted({c["kind"] for c in clips})}},
    }


def merge_periods(periods: list[tuple[float, float]], eps: float = 0.02) -> list[tuple[float, float]]:
    """Aneinandergrenzende Blur-Abschnitte (Gauß In + Rest) zu einer Spanne vereinen."""
    out: list[list[float]] = []
    for a, b in sorted(periods):
        if out and a <= out[-1][1] + eps:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _assign_blur(clips: list[dict], periods: list[tuple[float, float]], recipes: dict, warnings: list[str]) -> None:
    """Weichzeichner als Effekt am Standbild: je Artwork-Spanne 0 → Stärke → 0 (Rampen 0,5 s wie „Gauß In/Out“).

    Im Ursprungsschnitt liegt das Blur auf Einstellungsebenen; sichtbar ist es nur auf dem Standbild darunter, daher
    ist ein Weichzeichner direkt am Standbild gleichwertig und braucht keine Vorlage."""
    spec = recipes.get("blur", {})
    ein = spec.get("ein")
    if not ein or not periods:
        return
    strength = ein["keyframes"][-1][1]
    ramp = ein["keyframes"][-1][0]
    stills = [c for c in clips if c["kind"] == "still"]
    per_still: dict[int, list[tuple[float, float]]] = {}
    for a, b in periods:
        best = max(range(len(stills)), key=lambda i: min(b, stills[i]["end"]) - max(a, stills[i]["start"]), default=None)
        if best is None or min(b, stills[best]["end"]) - max(a, stills[best]["start"]) <= 0:
            warnings.append(f"Blur {a:.1f}–{b:.1f} s: kein Standbild darunter – übersprungen")
            continue
        per_still.setdefault(best, []).append((max(a, stills[best]["start"]), min(b, stills[best]["end"])))
    for i, ps in per_still.items():
        st = stills[i]["start"]
        kfs: list[list[float]] = []
        for a, b in ps:
            r = min(ramp, (b - a) / 2)
            for t, v in ((a - st, 0.0), (a - st + r, strength), (b - st - r, strength), (b - st, 0.0)):
                if not kfs or t > kfs[-1][0] + 1e-6:
                    kfs.append([round(t, 4), v])
        stills[i].setdefault("effects", []).append(
            {"id": "blur", "match_name": spec["match_name"], "params": [{"index": ein["param_index"], "name": ein["param"], "value": 0.0, "keyframes": kfs}]})
