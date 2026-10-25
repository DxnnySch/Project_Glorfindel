"""Liest Premiere-Effektvorgaben (.prfpset) und speichert sie als Rezepte (Heft §6).

Ein Rezept: Effekt, Verankerung am Clip-Anfang/-Ende und Keyframes relativ dazu (Sekunden).
Das Panel setzt die Keyframes selbst und kann pro Clip Werte (z. B. Konturfarbe) überschreiben.
"""
from __future__ import annotations

import json
from pathlib import Path

from defusedxml import ElementTree as ET

TICKS_PER_SECOND = 254_016_000_000
_STATIC_NAMES_SKIP = {" ", "Zufallsparameter"}


def _parse_keyframes(raw: str) -> list[tuple[int, str]]:
    out = []
    for item in (raw or "").split(";"):
        parts = item.split(",")
        if len(parts) >= 2 and parts[0].strip():
            out.append((int(parts[0]), parts[1].strip()))
    return out


def _num(v: str):
    try:
        f = float(v.rstrip("."))
        return int(f) if f.is_integer() and "." not in v else f
    except ValueError:
        return v


def parse_prfpset(path: Path | str) -> dict:
    root = ET.parse(str(path)).getroot()
    preset = root.find("FilterPreset")
    if preset is None:
        raise ValueError(f"{path}: kein FilterPreset gefunden")
    match = (preset.findtext("FilterMatchName") or "").strip()
    anchor_out = int(preset.findtext("AnchorOutPoint") or 0)
    comp = next((c for c in root.iter("VideoFilterComponent")), None)
    params: dict[str, object] = {}
    kf_times: list[int] = []
    raw: dict[str, list[tuple[int, str]]] = {}
    for p in root.iter("VideoComponentParam"):
        name = (p.findtext("Name") or "").strip()
        if not name or name in _STATIC_NAMES_SKIP:
            continue
        kfs = _parse_keyframes(p.findtext("Keyframes") or "")
        if kfs and (p.findtext("IsTimeVarying") or "").strip() == "true":
            raw[name] = kfs
            kf_times += [t for t, _ in kfs]
    anchor = "start"
    if kf_times and anchor_out and min(kf_times) > anchor_out * 0.5 and max(kf_times) >= anchor_out - TICKS_PER_SECOND:
        anchor = "end"
    base = anchor_out if anchor == "end" else 0
    for name, kfs in raw.items():
        params[name] = [[round((t - base) / TICKS_PER_SECOND, 4), _num(v)] for t, v in kfs]
    start_t = min(kf_times) - base if kf_times else 0
    end_t = max(kf_times) - base if kf_times else 0
    duration = round((end_t - start_t) / TICKS_PER_SECOND, 4)
    return {"match_name": match, "effect": match, "anchor": anchor, "duration": duration, "keyframes": params,
            "component": bool(comp is not None)}


def slug(name: str) -> str:
    """'Zoom schnell (1.0)' -> 'zoom_schnell', 'Gauß In' -> 'gauss_in', 'KarteIN' -> 'karte_in'."""
    import re
    n = name.replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    n = re.sub(r"\(.*?\)", "", n)
    n = re.sub(r"(?<=[a-z])(?=(?:IN|OUT|In|Out)$)", " ", n.strip())
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


def parse_effect(path: Path | str) -> dict | None:
    """Vorgabe mit EINEM Effekt als vollständiges Rezept für den Bauplan: alle Parameter (Index, Name, Wert) und Keyframes in Sekunden.

    Zeitbezug: Keyframes am Einblendpunkt der Vorgabe (AnchorInPoint) hängen am Clipanfang, solche am Ausblendpunkt am Clipende (negativ).
    Vorgaben mit mehreren Effekten (z. B. „Übergänge“) liefern None."""
    from .prproj_reader import parse_value
    root = ET.parse(str(path)).getroot()
    pr = root.find("FilterPreset")
    comps = list(root.iter("VideoFilterComponent"))
    if pr is None or len(comps) != 1:
        return None
    t_in = int(pr.findtext("AnchorInPoint") or 0)
    t_out = int(pr.findtext("AnchorOutPoint") or 0)
    by_id = {el.get("ObjectID"): el for el in root if el.get("ObjectID")}
    comp = comps[0]
    raw: list[tuple[int, str, str, list[tuple[int, str]]]] = []          # (Index, Name, Startwert, Keyframes)
    for ref in comp.iter("Param"):
        el = by_id.get(ref.get("ObjectRef"))
        if el is None:
            continue
        name = (el.findtext("Name") or "").strip()
        start = (el.findtext("StartKeyframe") or "").split(",")
        kfs = []
        if (el.findtext("IsTimeVarying") or "").strip() == "true":
            for item in (el.findtext("Keyframes") or "").split(";"):
                parts = item.split(",")
                if len(parts) >= 2 and parts[0].strip():
                    kfs.append((int(parts[0]), parts[1].strip()))
        raw.append((int(ref.get("Index")), name, start[1].strip() if len(start) > 1 else "", kfs))
    times = [t for *_, kfs in raw for t, _ in kfs]
    if times and min(times) - t_in > TICKS_PER_SECOND * 0.1 and t_out - max(times) <= TICKS_PER_SECOND * 0.1:
        anchor, base = "end", t_out
    else:
        anchor, base = "start", t_in
    params = []
    for idx, name, start, kfs in raw:
        if not name:
            continue
        e = {"index": idx, "name": name, "value": parse_value(start)}
        if kfs:
            e["keyframes"] = [[round((t - base) / TICKS_PER_SECOND, 4), parse_value(v)] for t, v in kfs]
        params.append(e)
    match = (pr.findtext("FilterMatchName") or "").strip()
    out = {"id": slug(Path(path).stem), "match_name": match, "display": (comp.findtext("Component/DisplayName") or "").strip(),
           "anchor": anchor, "params": params, "quelle": Path(path).name}
    if any(p["name"] == "Konturfarbe" for p in params):
        out["color_param"] = "Konturfarbe"
    return out


def effect_library(folder: Path | str) -> dict[str, dict]:
    """Alle Ein-Effekt-Vorgaben eines Ordners als Rezept-Bibliothek (Schlüssel = id)."""
    out = {}
    for f in sorted(Path(folder).glob("*.prfpset")):
        try:
            r = parse_effect(f)
        except Exception:  # noqa: BLE001
            r = None
        if r:
            out[r["id"]] = r
    return out


def import_folder(folder: Path | str) -> dict[str, dict]:
    """Alle .prfpset eines Ordners einlesen; Schlüssel = Dateiname ohne Endung."""
    out = {}
    for f in sorted(Path(folder).glob("*.prfpset")):
        try:
            out[f.stem] = parse_prfpset(f)
        except Exception as e:  # noqa: BLE001
            out[f.stem] = {"error": str(e)}
    return out


def save_recipes(recipes: dict[str, dict], dst: Path) -> None:
    dst.write_text(json.dumps(recipes, ensure_ascii=False, indent=2), encoding="utf-8")
