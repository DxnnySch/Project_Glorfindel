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
