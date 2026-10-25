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


def with_library(recipes: dict, library: dict[str, dict] | None) -> dict:
    """Rezepte um die Effekt-Bibliothek aus den .prfpset-Vorgaben ergänzen: Sie gehen den Rezepten aus dem Ursprungsprojekt vor,
    Gauß In/Out bestimmt den Weichzeichner."""
    out = dict(recipes)
    lib = dict(library or {})
    if "zoom_schnell" in lib:
        lib.setdefault("zoom", lib["zoom_schnell"])
    out["bibliothek"] = lib
    gin = lib.get("gauss_in")
    if gin:
        kp = next((p for p in gin["params"] if p.get("keyframes")), None)
        if kp:
            out["blur"] = {**recipes.get("blur", {}), "match_name": gin["match_name"], "display": gin.get("display", ""),
                           "ein": {"match_name": gin["match_name"], "param_index": kp["index"], "param": kp["name"],
                                   "keyframes": [[t, v] for t, v in kp["keyframes"]]}}
    return out


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
    by_id.update(recipes.get("bibliothek", {}))
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
                    if ta >= 0 and (c["anchor"] != "end" or ta <= max(dur, 0) + 1e-6):
                        kfs.append([round(max(ta, 0.0), 4), v])
                if kfs:
                    e["keyframes"] = kfs
            params.append(e)
        out.append({"id": c["id"], "match_name": c["match_name"], "display": c.get("display", ""), "params": params})
    return out


def _map_effect(dur: float, slide: float = 0.5) -> dict | None:
    """Karte: wie die Vorgaben „KarteIN/KarteOUT“ – Transformieren, Position gleitet in 0,5 s von oben (y=-0,5) in die Mitte und am Ende wieder hinaus."""
    if dur <= 2 * slide:
        return None
    top, mid = {"point": [0.5, -0.5]}, {"point": [0.5, 0.5]}
    kfs = [[0.0, top], [slide, mid], [round(dur - slide, 4), mid], [round(dur, 4), top]]
    return {"id": "karte", "match_name": "AE.ADBE Geometry", "display": "Transformieren",
            "params": [{"index": 1, "name": "Position", "value": mid, "keyframes": kfs}]}


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
    ep_off = float(env.premiere.get("ep_offset", 0.0))               # Referenz in Premiere liegt auf der Zeitachse der HQ-Datei
    clips: list[dict] = []
    nested: list[dict] = []                                           # Artwork-Sequenzen (Bild + Maske + Spurmaske-Key)
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
                clips.append({"kind": "episode", **base, "media": ep_id, "src_in": c["src_in"] + ep_off, "src_out": c["src_out"] + ep_off,
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
                mov = pr.get("pause_media") if c["name"] == "Pause" else pr.get("play_media")
                if mov:                                              # eigene .mov-Dateien (Pause.mov bzw. rückwärts als Play.mov)
                    clips.append({"kind": "anim", **base, "template": c["name"], "name": c["name"], "media": reg(Path(mov), "anim")})
                else:
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
                target_px = (pos["size"] * 1080) if pos else float(env.premiere.get("art_px", 1000.0))
                effects = _resolve_chain(recipes, [{"recipe": r} for r in env.premiere.get("artwork_effects", ("drop_shadow", "zoom", "fancy_out", "fancy_in"))], dur, contour, fps)
                position = [pos["x"], pos["y"]] if pos else [0.5, 0.5]
                mask = env.premiere.get("mask_path")
                if mask:
                    # Wie im Ursprungsschnitt: Bild + Maske in einer verschachtelten Sequenz, Spurmaske-Key; Effekte liegen auf der Sequenz.
                    nid = f"n{len(nested) + 1}"
                    nested.append({"id": nid, "name": f"Artwork {len(nested) + 1:02d} {f.stem}", "dur": dur, "image": reg(f, "artwork", size=list(size)),
                                   "mask": reg(Path(mask), "mask"), "image_track": 2, "mask_track": 4, "matte_track": 5,
                                   "image_scale": round(target_px / min(size) * 100, 3), "mask_scale": round(target_px / 800 * 100, 3),
                                   "position": position})
                    clip = {"kind": "artwork", **base, "nested": nid, "name": f.stem, "effects": effects}
                else:
                    clip = {"kind": "artwork", **base, "media": reg(f, "artwork", size=list(size)), "name": f.stem,
                            "crop": _square_crop(*size), "scale": round(target_px / min(size) * 100, 3), "position": position, "effects": effects}
                clips.append(clip)
            elif typ == "credit":
                art = {"credit_amazon": "amazon", "credit_artwork": "artwork", "credit_musik": "musik"}.get(c.get("slot", ""), "artwork")
                x = env.doppel.get("links" if c.get("layout") == "doppel_links" else "rechts", {}).get("x")                     if art == "artwork" and c.get("layout") in ("doppel_links", "doppel_rechts") else None
                png = env.credit(c["text"], art, x)
                clips.append({"kind": "credit", **base, "art": art, "media": reg(png, "credit"), "name": c["text"],
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
                clip = {"kind": "map", **base, "media": reg(f, "map"), "name": c.get("ref", "Karte")}
                fx = _resolve_chain(recipes, [{"recipe": r} for r in env.premiere.get("map_effects", ("karte_in", "karte_out"))], dur, None, fps)
                if not fx and _map_effect(dur):
                    fx = [_map_effect(dur)]
                if fx:
                    clip["effects"] = fx
                clips.append(clip)
    _amazon_vs_artist(clips)
    periods = merge_periods(blur_periods)
    _assign_blur(clips, periods, recipes, warnings)
    _adjust_blur(clips, periods, recipes, env.premiere.get("blur_track", 1))
    bars = env.premiere.get("bars_png")
    if bars and clips:
        clips.append({"kind": "bars", "start": 0.0, "end": snap(max(c["end"] for c in clips)), "track": env.premiere.get("bars_track", 7),
                      "scene": "", "media": reg(Path(bars), "bars"), "name": "Schwarzstreifen"})
    # Videospuren zuerst, je Spur nach Zeit; Premiere bekommt feste Reihenfolge für deterministische Ergebnisse
    clips.sort(key=lambda c: (0 if c["kind"] != "voice" else 1, c["track"], c["start"]))
    return {
        "schema": SCHEMA, "name": pkg["sequence"]["name"], "slug": pkg.get("slug", ""), "fps": fps,
        "episode_sequence": pkg["episode_sequence"], "bin": f"Glorfindel {pkg['sequence']['name']}",
        "adjustment_names": ["Einstellungsebene", "Adjustment Layer"],
        "anim_source": {"aep": env.premiere.get("aep", ""), "comp": env.premiere.get("comp", "Play-Pause")},
        "preset": {"path": env.premiere.get("preset", ""), "video_tracks": env.premiere.get("video_tracks", 14),
                   "audio_tracks": env.premiere.get("audio_tracks", 16)},
        "nested_preset": env.premiere.get("nested_preset", ""),
        "nested": nested, "media": list(media.values()), "clips": clips,
        "markers": [{"time": snap(m["time"]), "name": m["text"][:60], "comment": m["text"], "kind": m.get("kind", "")} for m in pkg.get("markers", [])],
        "warnings": warnings,
        "stats": {"clips": len(clips), "media": len(media), "duration": pkg.get("duration", 0.0),
                  "by_kind": {k: sum(1 for c in clips if c["kind"] == k) for k in sorted({c["kind"] for c in clips})}},
    }


def _amazon_vs_artist(clips: list[dict]) -> None:
    """„© amazon studios“ verschwindet, solange ein Künstler-Credit zu sehen ist (Ursprungsschnitt): Amazon-Credits werden an den Künstler-Credits aufgetrennt."""
    spans = sorted((c["start"], c["end"]) for c in clips if c["kind"] == "credit" and c.get("art") == "artwork")
    if not spans:
        return
    out: list[dict] = []
    for c in clips:
        if c["kind"] != "credit" or c.get("art") != "amazon":
            out.append(c)
            continue
        pieces = [(c["start"], c["end"])]
        for a, b in spans:
            nxt = []
            for x, y in pieces:
                if b <= x or a >= y:
                    nxt.append((x, y))
                    continue
                if a > x:
                    nxt.append((x, a))
                if b < y:
                    nxt.append((b, y))
            pieces = nxt
        for x, y in pieces:
            if y - x >= 0.1:
                out.append({**c, "start": round(x, 4), "end": round(y, 4)})
    clips[:] = out


def _adjust_blur(clips: list[dict], periods: list[tuple[float, float]], recipes: dict, track: int) -> None:
    """Gauß In/Out wie im Ursprungsschnitt: je Spanne eine Einstellungsebene (V2) über Film/Standbild, unter Bildern und Karten.
    Das Panel setzt sie, wenn das Projekt eine Einstellungsebene enthält; sonst gilt der Weichzeichner direkt am Standbild."""
    spec = recipes.get("blur", {})
    ein = spec.get("ein")
    if not ein:
        return
    strength, ramp = ein["keyframes"][-1][1], ein["keyframes"][-1][0]
    for a, b in periods:
        d = b - a
        r = min(ramp, d / 2)
        kfs = [[0.0, 0.0], [round(r, 4), strength], [round(d - r, 4), strength], [round(d, 4), 0.0]]
        clips.append({"kind": "adjust", "start": round(a, 4), "end": round(b, 4), "track": track, "scene": "", "name": "Gauß In/Out",
                      "effects": [{"id": "blur", "match_name": spec["match_name"], "params": [{"index": ein["param_index"], "name": ein["param"], "value": 0.0, "keyframes": kfs}]}]})


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
        stills[i].setdefault("fallback_effects", []).append(
            {"id": "blur", "match_name": spec["match_name"], "params": [{"index": ein["param_index"], "name": ein["param"], "value": 0.0, "keyframes": kfs}]})
