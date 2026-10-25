"""Abläufe mit Premiere: Medien vorbereiten, Rohschnitt in Premiere bauen, Proxy ↔ HQ tauschen.

Zustand dieser Maschine (Pfade lokaler Dateien) liegt im lokalen Cache der Folge, nicht in OneDrive.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import media, pipeline, prfpset, rough_cut, store
from .bridge import HUB, BridgeError
from .config import app_dir
from .premiere_media import EPISODE_FPS, EPISODE_SIZE, conform_reference, credit_png, play_pause_clips, bars_png
from .premiere_plan import PlanEnv, build_plan, load_recipes, with_library
from .premiere_preset import make_sequence_preset
from .progress import as_progress
from .service import Episode

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}


# ---------- Zustand ----------
def pdir(ep: Episode) -> Path:
    d = ep.p.cache() / "premiere"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_state(ep: Episode) -> dict:
    return store.read_json(pdir(ep) / "zustand.json", {"active": "proxy"})


def save_state(ep: Episode, st: dict) -> None:
    store.write_json(pdir(ep) / "zustand.json", st)


def remember_hq(ep: Episode, hq_file: str) -> None:
    """Vom HQ-Conform aufgerufen: diese Datei ist die zeitgleiche HQ-Fassung."""
    st = load_state(ep)
    st["hq"] = str(hq_file)
    save_state(ep, st)


def calibration() -> dict:
    return store.read_json(app_dir() / "bridge_calibration.json", {"colorMode": "unit", "keyframeBase": "clip"})


# ---------- Medien ----------
def ensure_reference(ep: Episode, pg=None) -> Path:
    """Konforme Referenz (konstante Bildrate, zugeschnitten): die Datei, die in Premiere liegt und aus der die Standbilder stammen."""
    pg = as_progress(pg)
    pr = ep.project()
    if not pr.reference_source:
        raise ValueError("Keine Referenz-Episode importiert (Quellen).")
    src = ep.source(pr.reference_source)
    srcfile = ep.source_path(src)
    dst = pdir(ep) / f"{ep.p.slug.replace(' ', '_')}_Referenz_CFR.mp4"
    if dst.exists() and dst.stat().st_mtime >= srcfile.stat().st_mtime:
        pg.fraction(1.0, "konforme Referenz ist aktuell")
        return dst
    pg.fraction(0.0, f"{src.path.rsplit('/', 1)[-1]} → konstante Bildrate {EPISODE_FPS:.3f} fps, {EPISODE_SIZE[0]}×{EPISODE_SIZE[1]}")
    conform_reference(srcfile, dst, crop=src.crop, on_progress=lambda f, info: pg.fraction(f, info.get("text")))
    return dst


def stills_from_file(scenes, media_file: Path, out_dir: Path, times: dict[str, float] | None = None, pg=None) -> dict[str, float]:
    """Standbilder (letztes Bild je Segment) aus genau dieser Datei ziehen. Rückgabe: Dateiname → Zeit in der Episode."""
    pg = as_progress(pg)
    times = times if times is not None else pipeline.still_times(scenes)
    info = media.probe(media_file)
    fps = info["fps"] or EPISODE_FPS
    for i, (name, t) in enumerate(times.items()):
        pg.sub(i, len(times), f"Standbild {name} bei {media.fmt_clock(t)}", "Standbilder")
        media.extract_still_last_frame(media_file, t, fps, out_dir / name, (info["width"], info["height"]))
    pg.sub(len(times), len(times), "alle Standbilder fertig", "Standbilder")
    return times


def _image_size(p: Path):
    try:
        if p.suffix.lower() in IMAGE_EXT:
            from PIL import Image
            with Image.open(p) as im:
                return im.size
        i = media.probe(p)
        return (i["width"], i["height"])
    except Exception:  # noqa: BLE001
        return None


def library_for(root: Path, presets_dir: str, templates_dir: Path) -> dict:
    """Effekt-Bibliothek: direkt aus dem Vorgaben-Ordner (immer aktuell), sonst der mitgelieferte Stand."""
    folder = Path(root) / presets_dir
    lib = prfpset.effect_library(folder) if folder.exists() else {}
    if lib:
        return lib
    snap = templates_dir / "effekt_bibliothek.json"
    return json.loads(snap.read_text(encoding="utf-8")) if snap.exists() else {}


def _library(ep: Episode, templates_dir: Path) -> dict:
    return library_for(ep.p.root, ep.settings.premiere.presets_dir, templates_dir)


def make_env(ep: Episode, templates_dir: Path, reference: Path, preset: Path, stills_dir: Path, nested_preset: Path | None = None) -> PlanEnv:
    tpl = rough_cut.load_template(templates_dir / "rohschnitt_vorlage.json" if (templates_dir / "rohschnitt_vorlage.json").exists() else None)
    s = ep.settings.premiere
    recipes_file = templates_dir / "premiere_rezepte.json"
    extra = {}
    pause_src = ep.p.root / s.pause_mov
    if pause_src.exists():
        try:
            extra["pause_media"], extra["play_media"] = (str(x) for x in play_pause_clips(pause_src, pdir(ep) / "anim"))
        except RuntimeError:
            pass                                                    # Rückfall: Komposition aus der .aep
    extra["bars_png"] = str(bars_png(pdir(ep) / "anim" / "Schwarzstreifen.png"))
    mask = templates_dir / "masken" / s.mask
    if mask.exists():
        extra["mask_path"] = str(mask)
    return PlanEnv(
        root=ep.p.root, episode_media=reference, stills_dir=stills_dir,
        credit=lambda text, art, x: credit_png(text, art, pdir(ep) / "credits", x_override=x),
        image_size=_image_size, recipes=with_library(load_recipes(recipes_file if recipes_file.exists() else None), _library(ep, templates_dir)), doppel=tpl["doppelbild"],
        premiere={"aep": str(ep.p.root / s.aep), "comp": s.comp, "pause_in": s.pause_in, "play_in": s.play_in,
                  "preset": str(preset), "video_tracks": s.video_tracks, "audio_tracks": s.audio_tracks,
                  "nested_preset": str(nested_preset or ""), "art_px": s.art_size_px,
                  "artwork_effects": list(s.artwork_effects), "map_effects": list(s.map_effects), **extra})


# ---------- Bauen ----------
def build_in_premiere(ep: Episode, templates_dir: Path, progress=None, by_strand: bool = True, hub=HUB) -> dict:
    pg = as_progress(progress)
    pg.plan([("Verbindung zu Premiere prüfen", 0.5), ("Konforme Referenz", 12), ("Schnittpaket berechnen", 2), ("Standbilder aus der Referenz", 8),
             ("Bauplan erstellen (Credits, Sequenz-Vorgabe)", 2), ("In Premiere bauen", 25), ("Bericht speichern", 0.5)])
    pg.step(0)
    if not hub.connected:
        raise BridgeError("Premiere ist nicht verbunden. In Premiere: Fenster → Erweiterungen → „Glorfindel Bridge“ öffnen.")
    pg.step(1)
    ref = ensure_reference(ep, pg)
    pg.step(2)
    res = pipeline.build_rough_cut(ep, templates_dir, with_stills=False, by_strand=by_strand, progress=None)
    pkg = json.loads(Path(res["json"]).read_text(encoding="utf-8"))
    scenes = pipeline.scenes_in_video(pipeline.ordered_scenes(ep, by_strand))
    pg.step(3)
    stills_dir = ep.p.stills / f"Bridge_v{res['version']}"     # eigener Ordner je Bau: Premiere sperrt Dateien aus früheren Importen
    times = stills_from_file(scenes, ref, stills_dir, pg=pg)
    pg.step(4)
    preset = make_sequence_preset(pdir(ep) / "Glorfindel-Rohschnitt.sqpreset", video_tracks=ep.settings.premiere.video_tracks,
                                  audio_tracks=ep.settings.premiere.audio_tracks)
    nested_preset = make_sequence_preset(pdir(ep) / "Glorfindel-Artwork.sqpreset", video_tracks=5, audio_tracks=1)
    plan = build_plan(pkg, make_env(ep, templates_dir, ref, preset, stills_dir, nested_preset))
    plan["calibration"] = calibration()
    plan["save"] = True
    store.write_json(pdir(ep) / f"bauplan_v{res['version']}.json", plan)
    pg.step(5, f"{plan['stats']['clips']} Clips, {plan['stats']['media']} Medien")

    def on_event(name, data):
        if name == "progress" and isinstance(data, dict):
            if data.get("of"):
                pg.sub(data.get("done", 0), data["of"], data.get("text", ""), "Clips")
            else:
                pg.fraction(0.0, data.get("text", ""))
    report = hub.call("plan.run", {"plan": plan}, timeout=3600, on_event=on_event)
    pg.step(6)
    st = load_state(ep)
    st.update({"ref_cfr": str(ref), "stills": times, "stills_dir": str(stills_dir), "active": "proxy", "version": res["version"],
               "sequence": plan["name"]})
    save_state(ep, st)
    store.write_json(pdir(ep) / f"bericht_v{res['version']}.json", report)
    store.log_change(ep.p.gl, ep.settings.user, f"Rohschnitt v{res['version']} in Premiere gebaut ({plan['stats']['clips']} Clips, {len(report.get('errors', []))} Fehler)")
    return {"version": res["version"], "sequence": plan["name"], "stats": plan["stats"], "report": report,
            "warnings": plan["warnings"] + report.get("warnings", [])}


# ---------- Tausch Proxy ↔ HQ ----------
def swap(ep: Episode, to: str, progress=None, hub=HUB) -> dict:
    """`to`: 'hq' oder 'proxy'. Tauscht nur die Dateien; Clips, Effekte und Handarbeit in Premiere bleiben."""
    pg = as_progress(progress)
    st = load_state(ep)
    if not st.get("ref_cfr") or not st.get("stills"):
        raise ValueError("Es gibt noch keinen in Premiere gebauten Rohschnitt dieser Folge.")
    if to == "hq" and not (st.get("hq") and Path(st["hq"]).exists()):
        raise ValueError("Die konforme HQ-Datei fehlt. Zuerst unter „Kontrolle“ Anker setzen und „HQ-Conform“ ausführen.")
    if st.get("active") == to:
        raise ValueError(f"Premiere arbeitet bereits mit der {'HQ-' if to == 'hq' else 'Proxy-'}Fassung.")
    if to == "hq":
        hq_fps = media.probe(Path(st["hq"]))["fps"] or 0.0
        if abs(hq_fps - EPISODE_FPS) > 0.01:
            raise ValueError(f"Die HQ-Datei hat {hq_fps:.3f} statt {EPISODE_FPS:.3f} Bildern pro Sekunde (ältere Conform-Version). "
                             "Bitte unter „Kontrolle“ den HQ-Conform noch einmal ausführen; dann lässt Premiere den Tausch zu.")
    pg.plan([("Verbindung prüfen", 0.5), ("HQ-Standbilder erzeugen" if to == "hq" else "Standbilder vorbereiten", 8), ("In Premiere tauschen", 2), ("Speichern", 0.5)])
    pg.step(0)
    if not hub.connected:
        raise BridgeError("Premiere ist nicht verbunden. Panel „Glorfindel Bridge“ in Premiere öffnen.")
    stills_dir = Path(st["stills_dir"])
    hq_dir = stills_dir.with_name(stills_dir.name + "_HQ")          # Parallelordner: nichts wird überschrieben, Premiere kann nichts sperren
    pg.step(1)
    if to == "hq":
        stills_from_file(None, Path(st["hq"]), hq_dir, times=st["stills"], pg=pg)
        swaps = [{"from": st["ref_cfr"], "to": st["hq"]}] + [{"from": str(stills_dir / n), "to": str(hq_dir / n)} for n in st["stills"]]
    else:
        swaps = [{"from": st["hq"], "to": st["ref_cfr"]}] + [{"from": str(hq_dir / n), "to": str(stills_dir / n)} for n in st["stills"]]
    pg.step(2)
    report = hub.call("media.swap", {"swaps": swaps, "refresh": []}, timeout=600)
    if report.get("fehler"):
        raise BridgeError("Tausch in Premiere unvollständig: " + "; ".join(f"{f.get('von') or f.get('datei')}: {f['fehler']}" for f in report["fehler"]))
    pg.step(3)
    st["active"] = to
    save_state(ep, st)
    store.log_change(ep.p.gl, ep.settings.user, f"Premiere auf {'HQ' if to == 'hq' else 'Proxy'} umgestellt ({len(st['stills'])} Standbilder, Episode)")
    return {"active": to, "report": report}


# ---------- Selbsttest ----------
def run_selftest(ep: Episode | None, progress=None, hub=HUB) -> dict:
    pg = as_progress(progress)
    if not hub.connected:
        raise BridgeError("Premiere ist nicht verbunden.")
    d = app_dir() / "bridge"
    d.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    png = d / "selbsttest.png"
    Image.new("RGB", (1000, 800), (60, 110, 200)).save(png)
    preset = make_sequence_preset(d / "selbsttest.sqpreset", video_tracks=14, audio_tracks=16)
    res = hub.call("selftest", {"png": str(png), "preset": str(preset)}, timeout=300,
                   on_event=lambda n, data: pg.fraction(0.5, (data or {}).get("text")) if n == "progress" else None)
    cal = {**calibration(), "colorMode": res.get("findings", {}).get("colorMode", "unit")}
    store.write_json(app_dir() / "bridge_calibration.json", cal)
    store.write_json(d / "selbsttest_bericht.json", res)
    return res
