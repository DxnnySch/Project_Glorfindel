"""Abläufe mit Premiere: Medien vorbereiten, Rohschnitt in Premiere bauen, Proxy ↔ HQ tauschen.

Zustand dieser Maschine (Pfade lokaler Dateien) liegt im lokalen Cache der Folge, nicht in OneDrive.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import media, mogrt_text, pipeline, prfpset, premiere_sync, premiere_tools, rough_cut, store
from .bridge import HUB, BridgeError
from .config import app_dir
from .timemap import TimeMap
from .premiere_media import audio_for, EPISODE_FPS, EPISODE_SIZE, conform_reference, credit_png, play_pause_clips, bars_png, remux_with_aac
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
    if st.get("direct"):
        return                                              # unveränderte HQ-Datei ist schon eingetragen
    st["hq"] = str(hq_file)
    save_state(ep, st)


def calibration() -> dict:
    return store.read_json(app_dir() / "bridge_calibration.json", {"colorMode": "unit", "keyframeBase": "source"})


# ---------- Medien ----------
NATIVE_FPS = (24000 / 1001, 24.0, 25.0, 30000 / 1001, 30.0)


def direct_hq(ep: Episode) -> dict | None:
    """HQ-Quelle, die ohne Umwandlung in Premiere eingesetzt werden kann: Zeitabbildung ist eine reine Verschiebung (gleiche Geschwindigkeit).
    Dann liegt die Referenz auf der Zeitachse der HQ-Datei (Schwarz davor) und die HQ-Datei bleibt unverändert, auch in ihrer Bildrate."""
    for src in ep.sources():
        if src.role != "hq" or not src.anchors:
            continue
        path = ep.source_path(src)
        if not path.exists():
            continue
        off = TimeMap(src.anchors).pure_offset()
        fps = next((f for f in NATIVE_FPS if abs(f - src.fps) < 0.01), None)
        if off is None or fps is None:
            continue
        return {"source": src, "file": path, "fps": fps, "offset": round(off * fps) / fps}
    return None


def _sync_episode_fps(ep: Episode, fps: float) -> None:
    pr = ep.project()
    if abs(pr.fps - fps) > 0.001:
        old, pr.fps = pr.fps, fps
        ep.save_project(pr)
        store.log_change(ep.p.gl, ep.settings.user, f"Bildrate der Folge von {old:.3f} auf {fps:.3f} fps gestellt (native Bildrate der HQ-Datei)")

def ensure_reference(ep: Episode, pg=None, offset: float = 0.0, audio: str = "aac", audio_src: Path | None = None) -> Path:
    """Konforme Referenz (konstante Bildrate, zugeschnitten, ggf. auf der Zeitachse der HQ-Datei): die Datei in Premiere, aus der die Standbilder stammen."""
    pg = as_progress(pg)
    pr = ep.project()
    if not pr.reference_source:
        raise ValueError("Keine Referenz-Episode importiert (Quellen).")
    src = ep.source(pr.reference_source)
    srcfile = ep.source_path(src)
    # mit Ton der HQ-Datei als eigene Datei: die ältere Referenz kann in Premiere geöffnet (gesperrt) sein
    dst = pdir(ep) / f"{ep.p.slug.replace(' ', '_')}_Referenz_CFR{'_TonAAC' if audio_src else ''}.mp4"
    side = dst.with_suffix(".json")
    want = {"fps": round(pr.fps, 4), "offset": round(offset, 4), "crop": src.crop, "audio": audio, "audio_src": str(audio_src) if audio_src else ""}
    newest = max(srcfile.stat().st_mtime, audio_src.stat().st_mtime if audio_src else 0)
    if dst.exists() and dst.stat().st_mtime >= newest and store.read_json(side, {}) == want:
        pg.fraction(1.0, "konforme Referenz ist aktuell")
        return dst
    extra = f", um {offset:.3f} s auf die Zeitachse der HQ-Datei verschoben" if offset else ""
    pg.fraction(0.0, f"{src.path.rsplit('/', 1)[-1]} → konstante Bildrate {pr.fps:.3f} fps, {EPISODE_SIZE[0]}×{EPISODE_SIZE[1]}{extra}")
    conform_reference(srcfile, dst, crop=src.crop, fps=pr.fps, offset=offset, audio_codec=audio, audio_src=audio_src, on_progress=lambda f, info: pg.fraction(f, info.get("text")))
    store.write_json(side, want)
    return dst


def still_file(st: dict, name: str) -> str:
    """Dateiname eines Standbilds: nach einem Abgleich mit Premiere bekommt es eine neue Fassung („1_r1.png“), damit Premiere nichts sperrt."""
    rev = (st.get("still_rev") or {}).get(name, 0)
    return name if not rev else f"{Path(name).stem}_r{rev}{Path(name).suffix}"


def stills_from_file(scenes, media_file: Path, out_dir: Path, times: dict[str, float] | None = None, pg=None, reuse: bool = False,
                     files: dict[str, str] | None = None) -> dict[str, float]:
    """Standbilder (letztes Bild je Segment) aus genau dieser Datei ziehen. Rückgabe: Dateiname → Zeit in der Episode."""
    pg = as_progress(pg)
    times = times if times is not None else pipeline.still_times(scenes, fps)
    info = media.probe(media_file)
    fps = info["fps"] or EPISODE_FPS
    for i, (name, t) in enumerate(times.items()):
        pg.sub(i, len(times), f"Standbild {name} bei {media.fmt_clock(t)}", "Standbilder")
        fname = (files or {}).get(name, name)
        target = out_dir / fname
        if reuse and target.exists() and target.stat().st_size > 0 and target.stat().st_mtime >= media_file.stat().st_mtime:
            continue                                         # nach abgebrochenem Tausch schon vorhanden (evtl. von Premiere geöffnet)
        media.extract_still_last_frame(media_file, t, fps, target, (info["width"], info["height"]))
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


def discover_credit_mogrts(folder: Path) -> dict[str, str]:
    """Credit-Vorlagen (editierbarer Text) aus vorlagen/mogrt: „Credit Amazon.mogrt“, „Credit Artwork.mogrt“, „Credit Musik.mogrt“.
    Gibt es neuere Exporte („Credit Amazon v2.mogrt“), gilt die höchste Nummer. Fehlt eine Art, bleibt dafür das PNG."""
    out: dict[str, str] = {}
    if Path(folder).is_dir():
        files = [f for f in Path(folder).iterdir() if f.suffix.lower() == ".mogrt"]
        for art in ("amazon", "artwork", "musik"):
            best: tuple[int, Path] | None = None
            for f in files:
                m = re.fullmatch(rf"credit {art}(?: v(\d+))?", f.stem.lower())
                if m and (best is None or int(m.group(1) or 0) > best[0]):
                    best = (int(m.group(1) or 0), f)
            if best:
                out[art] = str(best[1])
    return out


def library_for(root: Path, presets_dir: str, templates_dir: Path) -> dict:
    """Effekt-Bibliothek: direkt aus dem Vorgaben-Ordner (immer aktuell), sonst der mitgelieferte Stand."""
    folder = Path(root) / presets_dir
    lib = prfpset.effect_library(folder) if folder.exists() else {}
    if lib:
        return lib
    snap = templates_dir / "effekt_bibliothek.json"
    return json.loads(snap.read_text(encoding="utf-8")) if snap.exists() else {}


def _text_mogrt(template: Path, text: str, folder: Path) -> Path | None:
    """Vorlage mit fest eingetragenem Text; bei unbekanntem Aufbau der Vorlage None (dann versucht das Panel den Text zu setzen, sonst PNG)."""
    try:
        return mogrt_text.text_mogrt(template, text, folder)
    except Exception:  # noqa: BLE001 – defekte oder fremde Vorlage soll den Bau nicht verhindern
        return None


def _library(ep: Episode, templates_dir: Path) -> dict:
    return library_for(ep.p.root, ep.settings.premiere.presets_dir, templates_dir)


def make_env(ep: Episode, templates_dir: Path, reference: Path, preset: Path, stills_dir: Path, nested_preset: Path | None = None,
             ep_offset: float = 0.0) -> PlanEnv:
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
    masks = templates_dir / "masken"
    if (masks / "Maske Quadrat.png").exists() and (masks / "Maske.png").exists():
        extra["mask_dir"] = str(masks)
        extra["mask_mode"] = s.mask
        extra["landscape_px"] = s.landscape_px
    credit_mogrt = discover_credit_mogrts(templates_dir / "mogrt")
    if credit_mogrt:
        extra["credit_mogrt"] = credit_mogrt
    from .autoframe import subject_box
    from .llm import Llm
    llm = Llm(ep.settings)
    cache_file = pdir(ep) / "autoframe.json"
    return PlanEnv(
        root=ep.p.root, episode_media=reference, stills_dir=stills_dir,
        credit=lambda text, art, x: credit_png(text, art, pdir(ep) / "credits", x_override=x),
        frame_box=lambda p: subject_box(llm, p, cache_file),
        credit_mogrt=lambda tpl, text: _text_mogrt(Path(tpl), text, pdir(ep) / "mogrt"),
        image_size=_image_size, recipes=with_library(load_recipes(recipes_file if recipes_file.exists() else None), _library(ep, templates_dir)), doppel=tpl["doppelbild"],
        premiere={"aep": str(ep.p.root / s.aep), "comp": s.comp, "pause_in": s.pause_in, "play_in": s.play_in,
                  "preset": str(preset), "video_tracks": s.video_tracks, "audio_tracks": s.audio_tracks,
                  "nested_preset": str(nested_preset or ""), "art_px": s.art_size_px,
                  "artwork_effects": list(s.artwork_effects), "map_effects": list(s.map_effects), "ep_offset": ep_offset, **extra})


# ---------- Bauen ----------
def build_in_premiere(ep: Episode, templates_dir: Path, progress=None, by_strand: bool = True, hub=HUB, audio_order: bool = False) -> dict:
    pg = as_progress(progress)
    pg.plan([("Verbindung zu Premiere prüfen", 0.5), ("Konforme Referenz", 12), ("Schnittpaket berechnen", 2), ("Standbilder aus der Referenz", 8),
             ("Bauplan erstellen (Credits, Sequenz-Vorgabe)", 2), ("In Premiere bauen", 25), ("Bericht speichern", 0.5)])
    pg.step(0)
    if not hub.connected:
        raise BridgeError("Premiere ist nicht verbunden. In Premiere: Fenster → Erweiterungen → „Glorfindel Bridge“ öffnen.")
    premiere_tools.remember_episode(ep)                     # die Panel-Werkzeuge arbeiten mit den Einstellungen dieser Folge
    pg.step(1)
    direct = direct_hq(ep)
    if direct:
        _sync_episode_fps(ep, direct["fps"])
    off = direct["offset"] if direct else 0.0
    audio = audio_for(media.probe(direct["file"]).get("acodec", "")) if direct else "aac"
    ref = ensure_reference(ep, pg, off, audio, Path(direct["file"]) if direct else None)
    pg.step(2)
    res = pipeline.build_rough_cut(ep, templates_dir, with_stills=False, by_strand=by_strand, progress=None, audio_order=audio_order)
    pkg = json.loads(Path(res["json"]).read_text(encoding="utf-8"))
    scenes = pipeline.rough_cut_scenes(ep, by_strand, audio_order)
    pg.step(3)
    stills_dir = ep.p.stills / f"Bridge_v{res['version']}"     # eigener Ordner je Bau: Premiere sperrt Dateien aus früheren Importen
    fps_ep = ep.project().fps
    times = {n: round(t + off, 6) for n, t in pipeline.still_times(scenes, fps_ep).items()}      # Zeitachse der Referenz in Premiere (= HQ-Zeit)
    stills_from_file(None, ref, stills_dir, times=times, pg=pg)
    pg.step(4)
    seq_fps = ep.settings.premiere.sequence_fps
    preset = make_sequence_preset(pdir(ep) / f"Glorfindel-Rohschnitt-{seq_fps:g}fps.sqpreset", video_tracks=ep.settings.premiere.video_tracks,
                                  audio_tracks=ep.settings.premiere.audio_tracks, fps=seq_fps)
    nested_preset = make_sequence_preset(pdir(ep) / f"Glorfindel-Artwork-{seq_fps:g}fps.sqpreset", video_tracks=5, audio_tracks=1, fps=seq_fps)
    plan = build_plan(pkg, make_env(ep, templates_dir, ref, preset, stills_dir, nested_preset, ep_offset=off))
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
               "sequence": plan["name"], "ep_offset": off, "direct": bool(direct), "by_strand": by_strand, "still_rev": {}})
    if direct:
        st["hq"] = str(direct["file"])                      # die unveränderte HQ-Datei: kein Conform nötig
    save_state(ep, st)
    store.write_json(pdir(ep) / f"bericht_v{res['version']}.json", report)
    store.log_change(ep.p.gl, ep.settings.user, f"Rohschnitt v{res['version']} in Premiere gebaut ({plan['stats']['clips']} Clips, {len(report.get('errors', []))} Fehler)")
    return {"version": res["version"], "sequence": plan["name"], "stats": plan["stats"], "report": report,
            "warnings": plan["warnings"] + report.get("warnings", [])}


# ---------- Tausch Proxy ↔ HQ ----------
def hq_for_premiere(ep: Episode, hq: Path, ref_acodec: str, pg=None) -> Path:
    """Die HQ-Datei, die Premiere bekommt: hat sie ein anderes Tonformat als die Referenz in Premiere (z. B. Dolby gegen AAC), lässt Premiere den Tausch nicht zu.
    Dann wird eine Kopie mit unverändertem Bild und AAC-Ton angelegt (einmal je HQ-Datei)."""
    if audio_for(media.probe(hq).get("acodec", "")) == audio_for(ref_acodec):
        return hq
    dst = pdir(ep) / f"{hq.stem}_AAC.mp4"
    if dst.exists() and dst.stat().st_mtime >= hq.stat().st_mtime:
        return dst
    pg = as_progress(pg)
    pg.fraction(0.0, "HQ-Datei mit AAC-Ton für Premiere (Bild unverändert) …")
    return remux_with_aac(hq, dst, on_progress=lambda f, info: pg.fraction(f, info.get("text")))


def show_scene(ep: Episode, scene_id: str, hub=HUB) -> dict:
    """Den Abspielkopf in Premiere an den Anfang einer Szene setzen (Zeit aus dem letzten Bauplan)."""
    st = load_state(ep)
    plan_file = pdir(ep) / f"bauplan_v{st.get('version')}.json"
    if not st.get("version") or not plan_file.exists():
        raise ValueError("Noch kein Rohschnitt gebaut: Szenen sind erst nach dem Bau in Premiere.")
    from types import SimpleNamespace
    t = premiere_tools.scene_start(SimpleNamespace(plan=store.read_json(plan_file, {})), scene_id)
    return {"time": t, **hub.call("sequence.seek", {"time": t}, timeout=30)}


def swap(ep: Episode, to: str, progress=None, hub=HUB) -> dict:
    """`to`: 'hq' oder 'proxy'. Tauscht nur die Dateien; Clips, Effekte und Handarbeit in Premiere bleiben."""
    pg = as_progress(progress)
    st = load_state(ep)
    if not st.get("ref_cfr") or not st.get("stills"):
        raise ValueError("Es gibt noch keinen in Premiere gebauten Rohschnitt dieser Folge.")
    premiere_tools.remember_episode(ep)
    if to == "hq" and not (st.get("hq") and Path(st["hq"]).exists()):
        raise ValueError("Die konforme HQ-Datei fehlt. Zuerst unter „Kontrolle“ Anker setzen und „HQ-Conform“ ausführen.")
    if st.get("active") == to:
        raise ValueError(f"Premiere arbeitet bereits mit der {'HQ-' if to == 'hq' else 'Proxy-'}Fassung.")
    if to == "hq":
        hq_fps = media.probe(Path(st["hq"]))["fps"] or 0.0
        ref_fps = media.probe(Path(st["ref_cfr"]))["fps"] or EPISODE_FPS
        if abs(hq_fps - ref_fps) > 0.01:
            raise ValueError(f"Die HQ-Datei hat {hq_fps:.3f} statt {ref_fps:.3f} Bildern pro Sekunde wie die Referenz in Premiere. "
                             "Bitte unter „Kontrolle“ den HQ-Conform noch einmal ausführen (oder den Rohschnitt neu bauen); dann lässt Premiere den Tausch zu.")
    pg.plan([("Verbindung prüfen", 0.5), ("HQ-Standbilder erzeugen" if to == "hq" else "Standbilder vorbereiten", 8), ("In Premiere tauschen", 2), ("Speichern", 0.5)])
    pg.step(0)
    if not hub.connected:
        raise BridgeError("Premiere ist nicht verbunden. Panel „Glorfindel Bridge“ in Premiere öffnen.")
    stills_dir = Path(st["stills_dir"])
    hq_dir = stills_dir.with_name(stills_dir.name + "_HQ")          # Parallelordner: nichts wird überschrieben, Premiere kann nichts sperren
    pg.step(1)
    if to == "hq":
        hq_file = hq_for_premiere(ep, Path(st["hq"]), media.probe(Path(st["ref_cfr"])).get("acodec", ""), pg)
        st["hq_pr"] = str(hq_file)                                  # die Datei, die in Premiere liegt (für den Rückweg)
        stills_from_file(None, Path(st["hq"]), hq_dir, times=st["stills"], pg=pg, reuse=True, files={n: still_file(st, n) for n in st["stills"]})
        swaps = [{"from": st["ref_cfr"], "to": str(hq_file)}] + [{"from": str(stills_dir / still_file(st, n)), "to": str(hq_dir / still_file(st, n))} for n in st["stills"]]
    else:
        swaps = [{"from": st.get("hq_pr") or st["hq"], "to": st["ref_cfr"]}] + [{"from": str(hq_dir / still_file(st, n)), "to": str(stills_dir / still_file(st, n))} for n in st["stills"]]
    pg.step(2)
    report = hub.call("media.swap", {"swaps": swaps, "refresh": [], "bin": f"Glorfindel {st['sequence']}" if st.get("sequence") else None}, timeout=600)
    if report.get("fehler"):
        raise BridgeError("Tausch in Premiere unvollständig: " + "; ".join(f"{f.get('von') or f.get('datei')}: {f['fehler']}" for f in report["fehler"]))
    pg.step(3)
    st["active"] = to
    save_state(ep, st)
    store.log_change(ep.p.gl, ep.settings.user, f"Premiere auf {'HQ' if to == 'hq' else 'Proxy'} umgestellt ({len(st['stills'])} Standbilder, Episode)")
    return {"active": to, "report": report}


# ---------- Abgleich mit Premiere ----------
def _model_stills(ep: Episode, st: dict) -> dict[str, float]:
    """Standbild-Zeiten, wie das Modell sie heute verlangt (Zeitachse der Referenz in Premiere)."""
    scenes = pipeline.scenes_in_video(pipeline.ordered_scenes(ep, st.get("by_strand", True)))
    off = st.get("ep_offset", 0.0)
    return {n: round(t + off, 6) for n, t in pipeline.still_times(scenes, ep.project().fps).items()}


def sync_state(ep: Episode) -> dict:
    """Anzeige „muss nach Premiere getauscht werden?“: Standbilder, die nicht mehr zu den Segmenten der App passen."""
    st = load_state(ep)
    if not st.get("stills"):
        return {"gebaut": False, "tausch": [], "struktur": False}
    r = premiere_sync.stale_stills(_model_stills(ep, st), st["stills"])
    return {"gebaut": True, "tausch": sorted(r["tausch"], key=lambda n: int(Path(n).stem)), "struktur": r["struktur"]}


def read_from_premiere(ep: Episode, apply: bool = False, progress=None, hub=HUB) -> dict:
    """Serienclips aus der gebauten Sequenz lesen und mit den Segmenten der App vergleichen; `apply` übernimmt die Änderungen."""
    pg = as_progress(progress)
    st = load_state(ep)
    if not st.get("sequence"):
        raise ValueError("Es gibt noch keinen in Premiere gebauten Rohschnitt dieser Folge.")
    if not hub.connected:
        raise BridgeError("Premiere ist nicht verbunden. Panel „Glorfindel Bridge“ in Premiere öffnen.")
    pg.plan([("Sequenz aus Premiere lesen", 4), ("Mit den Segmenten vergleichen", 0.5), ("Segmente übernehmen", 0.5)])
    pg.step(0)
    dump = hub.call("sequence.dump", {"name": st["sequence"], "params": False, "maxItems": 5000}, timeout=300)
    pg.step(1)
    pieces = premiere_sync.pieces_from_dump(dump, st.get("ep_offset", 0.0))
    scenes = ep.scenes()
    changes = premiere_sync.compare(scenes, pieces, ep.project().fps)
    pg.step(2)
    applied = False
    if apply:
        for sc in premiere_sync.apply(scenes, changes):
            ep.save_scene(sc, "Segmente aus Premiere übernommen")
        n = sum(1 for c in changes if c["typ"] in ("geaendert", "geteilt"))
        if n:
            store.log_change(ep.p.gl, ep.settings.user, f"{n} Segment(e) aus Premiere übernommen")
        applied = True
    return {"changes": changes, "angewendet": applied, "sync": sync_state(ep), "sequence": st["sequence"]}


def refresh_stills(ep: Episode, progress=None, hub=HUB) -> dict:
    """Ersetzt in Premiere die Standbilder, die nach einer Änderung der Segmente nicht mehr stimmen. Der Schnitt bleibt unverändert."""
    pg = as_progress(progress)
    st = load_state(ep)
    sy = sync_state(ep)
    if not sy["gebaut"]:
        raise ValueError("Es gibt noch keinen in Premiere gebauten Rohschnitt dieser Folge.")
    if sy["struktur"]:
        raise ValueError("Die Standbilder der App passen nicht mehr zur Anzahl im Rohschnitt in Premiere (Segmente oder Kommentare wurden verändert). Bitte den Rohschnitt neu bauen.")
    if not sy["tausch"]:
        return {"getauscht": 0, "namen": []}
    if not hub.connected:
        raise BridgeError("Premiere ist nicht verbunden. Panel „Glorfindel Bridge“ in Premiere öffnen.")
    hq = st.get("active") == "hq"
    media_file = Path(st["hq"] if hq else st["ref_cfr"])
    stills_dir = Path(st["stills_dir"])
    out_dir = stills_dir.with_name(stills_dir.name + "_HQ") if hq else stills_dir
    new_times = _model_stills(ep, st)
    pg.plan([("Neue Standbilder erzeugen", 6), ("In Premiere tauschen", 2), ("Speichern", 0.5)])
    pg.step(0)
    revs = dict(st.get("still_rev") or {})
    swaps, files = [], {}
    for n in sy["tausch"]:
        old = still_file(st, n)
        revs[n] = revs.get(n, 0) + 1
        files[n] = still_file({"still_rev": revs}, n)
        swaps.append({"from": str(out_dir / old), "to": str(out_dir / files[n])})
    stills_from_file(None, media_file, out_dir, times={n: new_times[n] for n in sy["tausch"]}, pg=pg, files=files)
    pg.step(1)
    report = hub.call("media.swap", {"swaps": swaps, "refresh": [], "bin": f"Glorfindel {st['sequence']}" if st.get("sequence") else None}, timeout=600)
    if report.get("fehler"):
        raise BridgeError("Tausch in Premiere unvollständig: " + "; ".join(f"{f.get('von') or f.get('datei')}: {f['fehler']}" for f in report["fehler"]))
    pg.step(2)
    st["stills"] = {**st["stills"], **{n: new_times[n] for n in sy["tausch"]}}
    st["still_rev"] = revs
    save_state(ep, st)
    store.log_change(ep.p.gl, ep.settings.user, f"{len(swaps)} Standbild(er) in Premiere aktualisiert")
    return {"getauscht": len(swaps), "namen": sy["tausch"], "report": report}


# ---------- Selbsttest ----------
def run_selftest(ep: Episode | None, progress=None, hub=HUB, templates_dir: Path | None = None) -> dict:
    pg = as_progress(progress)
    if not hub.connected:
        raise BridgeError("Premiere ist nicht verbunden.")
    d = app_dir() / "bridge"
    d.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    png = d / "selbsttest.png"
    Image.new("RGB", (1000, 800), (60, 110, 200)).save(png)
    preset = make_sequence_preset(d / "selbsttest.sqpreset", video_tracks=14, audio_tracks=16)
    mogrts = discover_credit_mogrts(templates_dir / "mogrt") if templates_dir else {}
    res = hub.call("selftest", {"png": str(png), "preset": str(preset), "mogrts": mogrts}, timeout=300,
                   on_event=lambda n, data: pg.fraction(0.5, (data or {}).get("text")) if n == "progress" else None)
    cal = {**calibration(), "colorMode": res.get("findings", {}).get("colorMode", "unit")}
    store.write_json(app_dir() / "bridge_calibration.json", cal)
    store.write_json(d / "selbsttest_bericht.json", res)
    return res
