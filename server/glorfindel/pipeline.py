"""Orchestrierung über mehrere Module hinweg (ohne HTTP): Abgleich, Standbilder, Rohschnitt, Assets, Karten."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import align, align_bullets, fcpxml, media, rough_cut, stt, store
from .conform import render_stills_from_hq
from .models import Anchor, Scene
from .scenes import normalize_block, sort_scenes
from .service import Episode
from .timemap import TimeMap

STILL_SIZE = (1920, 800)


# ---------- Reihenfolge ----------
def ordered_scenes(ep: Episode, by_strand: bool = True) -> list[Scene]:
    scenes = ep.scenes()
    return sort_scenes(scenes, ep.strands()) if by_strand else scenes


# ---------- Assets / Karten (JSON je Eintrag) ----------
def load_assets(ep: Episode) -> dict[str, dict]:
    out = {}
    for f in sorted(ep.p.assets.glob("*.json")):
        d = store.read_json(f)
        if d and d.get("id"):
            out[d["id"]] = d
    return out


def save_asset(ep: Episode, data: dict) -> dict:
    if not data.get("id"):
        nums = [int(m[1]) for k in load_assets(ep) if (m := re.match(r"art_(\d+)", k))]
        data["id"] = f"art_{max(nums, default=0) + 1:04d}"
    store.write_json(ep.p.assets / f"{data['id']}.json", data)
    store.log_change(ep.p.gl, ep.settings.user, f"Asset {data['id']} gespeichert")
    return data


def load_maps(ep: Episode) -> dict[str, dict]:
    out = {}
    for f in sorted(ep.p.maps.glob("*.json")):
        d = store.read_json(f)
        if d and d.get("id"):
            out[d["id"]] = d
    return out


def save_map(ep: Episode, data: dict) -> dict:
    store.write_json(ep.p.maps / f"{data['id']}.json", data)
    store.log_change(ep.p.gl, ep.settings.user, f"Karte {data['id']} gespeichert")
    return data


# ---------- Aufnahme ----------
def alignment_path(ep: Episode) -> Path:
    return ep.p.recording / "abgleich.json"


def load_alignment(ep: Episode) -> dict:
    return store.read_json(alignment_path(ep), {"recordings": [], "scenes": {}})


def save_alignment(ep: Episode, data: dict) -> None:
    store.write_json(alignment_path(ep), data)


def add_recording(ep: Episode, path: str, speaker: str) -> dict:
    data = load_alignment(ep)
    rid = f"r_{speaker}_{len(data['recordings']) + 1}"
    from .paths import to_rel
    abs_path = Path(path) if Path(path).is_absolute() else ep.p.root / path
    info = media.probe(abs_path)
    data["recordings"].append({"id": rid, "speaker": speaker, "path": to_rel(ep.p.root, abs_path),
                               "duration": info["duration"]})
    save_alignment(ep, data)
    store.log_change(ep.p.gl, ep.settings.user, f"Aufnahme {rid} hinzugefügt")
    return data["recordings"][-1]


def _fix_transcript_with_llm(tr: list[dict], llm, chunk: int = 120) -> list[dict]:
    """Eigennamen per LLM nachkorrigieren; nur wortweise 1:1 übernehmen, wenn die Wortzahl stimmt."""
    out = [dict(w) for w in tr]
    for i in range(0, len(out), chunk):
        part = out[i:i + chunk]
        fixed = llm.fix_transcript(" ".join(w["w"] for w in part), align.TOLKIEN_GLOSSARY).split()
        if len(fixed) == len(part):
            for w, f in zip(part, fixed):
                w["w"] = f
    return out


def transcribe_recording(ep: Episode, rec: dict, llm=None, progress=lambda p: None) -> list[dict]:
    cache = ep.p.recording / f"transkript_{rec['id']}.json"
    tr = store.read_json(cache)
    if tr is None:
        path = ep.p.root / rec["path"]
        backend = stt.choose_backend(ep.settings.transcription)
        if backend == "keins":
            raise RuntimeError("Für die Transkription fehlt Whisper. Entweder lokal installieren (install-Skript, Option Whisper) "
                               "oder in den Einstellungen „ScaDS.AI Whisper“ wählen (sendet die Aufnahme an ScaDS.AI).")
        if not path.exists():
            raise FileNotFoundError(f"Aufnahme nicht gefunden: {rec['path']}")
        if backend == "scads":
            if llm is None or llm.client is None:
                raise RuntimeError("ScaDS-Transkription gewählt, aber kein API-Schlüssel (.env) gefunden")
            tr = stt.transcribe_remote(path, llm.client, progress_cb=progress)
        else:
            tr = align.transcribe(path, ep.settings.whisper_model, progress_cb=progress)
        if llm is not None and llm.enabled("transcript_fix"):
            tr = _fix_transcript_with_llm(tr, llm)
        store.write_json(cache, tr)
    return tr


def run_alignment(ep: Episode, llm=None, prefer: str = "last", progress=lambda p: None,
                  transcripts: dict[str, list[dict]] | None = None) -> dict:
    """Transkribiert (falls nötig) und gleicht alle Aufnahmen mit dem Skript ab."""
    data = load_alignment(ep)
    scenes = ordered_scenes(ep)
    results: dict[str, list[dict]] = {}
    n = max(1, len(data["recordings"]))
    for k, rec in enumerate(data["recordings"]):
        tr = (transcripts or {}).get(rec["id"]) or transcribe_recording(
            ep, rec, llm, lambda p, k=k: progress((k + p * 0.8) / n))
        text_units, bullet_units = [], []
        for sc in scenes:
            for bi, blk in enumerate(sc.kommentar):
                if rec["speaker"] not in ("alle", blk.sprecher):
                    continue
                if blk.modus == "stichpunkte":
                    bullet_units.append((sc.id, bi, blk.stichpunkte))
                elif blk.text.strip():
                    text_units.append((sc.id, bi, blk.text))
        parts = [align.align_recording(text_units, tr, rec["id"], prefer=prefer),
                 align_bullets.align_bullets(bullet_units, tr, rec["id"])]
        for part in parts:
            for sid, blocks in part.items():
                results.setdefault(sid, []).extend(blocks)
        progress((k + 1) / n)
    # manuelle Korrekturen aus früheren Läufen erhalten
    for sid, blocks in data.get("scenes", {}).items():
        for old in blocks:
            if old.get("manual"):
                new = results.setdefault(sid, [])
                new[:] = [b for b in new if b["block"] != old["block"]] + [old]
    data["scenes"] = {sid: sorted(bl, key=lambda b: b["block"]) for sid, bl in results.items()}
    save_alignment(ep, data)
    # Status der Szenen
    for sc in scenes:
        bl = data["scenes"].get(sc.id, [])
        if sc.kommentar and bl and all(not b.get("missing") for b in bl) and len(bl) == len(sc.kommentar):
            sc.status = "abgeglichen"
            ep.save_scene(sc, f"Szene {sc.id} abgeglichen")
    store.log_change(ep.p.gl, ep.settings.user, "Aufnahme-Abgleich ausgeführt")
    return data


def set_block_timing(ep: Episode, scene_id: str, block: int, t_in: float, t_out: float) -> dict:
    """Grenzen per Hand korrigieren (Prüfansicht)."""
    data = load_alignment(ep)
    blocks = data["scenes"].setdefault(scene_id, [])
    entry = next((b for b in blocks if b["block"] == block), None)
    if entry is None:
        rec = data["recordings"][0]["id"] if data["recordings"] else ""
        entry = {"block": block, "rec": rec}
        blocks.append(entry)
    entry.update(missing=False, manual=True, **{"in": t_in, "out": t_out})
    entry.pop("missing", None)
    save_alignment(ep, data)
    return entry


def adopt_spoken_text(ep: Episode, scene_id: str, block: int) -> Scene:
    """Gesprochenen Text (Stichpunkt-Block) als Skript übernehmen; Anker wandern auf Wörter."""
    data = load_alignment(ep)
    res = next((b for b in data["scenes"].get(scene_id, []) if b["block"] == block), None)
    if not res or "gesprochen" not in res:
        raise ValueError("Für diesen Block liegt kein gesprochener Text vor")
    sc = ep.scene(scene_id)
    align_bullets.adopt_spoken(sc.kommentar[block], res)
    ep.save_scene(sc, f"Szene {scene_id}: gesprochener Text übernommen")
    return sc


# ---------- Standbilder ----------
def still_times(scenes: list[Scene]) -> dict[str, float]:
    """Dateiname -> Episodenzeit des Standbild-Frames (letzter Frame bzw. erster, je Szene)."""
    out = {}
    for n, sc in enumerate(scenes, 1):
        if sc.standbild == "aus" or not sc.segmente:
            continue
        out[f"{n}.png"] = sc.segmente[-1].out if sc.standbild == "ende" else sc.segmente[0].in_
    return out


def render_stills(ep: Episode, scenes: list[Scene], source_id: str | None = None, progress=lambda p: None) -> dict:
    """Standbilder aus der gewählten Quelle (Standard: Referenz). HQ-Quellen landen im Parallelordner."""
    pr = ep.project()
    sid = source_id or pr.reference_source
    src = ep.source(sid)
    tm = TimeMap(src.anchors) if src.role != "referenz" else TimeMap([])
    out_dir = ep.p.stills if src.role in ("referenz", "screener", "screencapture") else ep.p.base / "Videoelemente_HQ"
    times = still_times(scenes)
    path = ep.source_path(src)
    done = {}
    fps = src.fps or pr.fps
    for i, (name, t) in enumerate(times.items()):
        done[name] = str(media.extract_still_last_frame(path, tm.ref_to_src(t), fps, out_dir / name, STILL_SIZE)
                         if src.crop is None else _crop_still(path, tm.ref_to_src(t), fps, out_dir / name, src.crop))
        progress((i + 1) / max(1, len(times)))
    return {"dir": str(out_dir), "files": done}


def _crop_still(path: Path, t: float, fps: float, dst: Path, crop: list[int]) -> Path:
    """Standbild aus einer zugeschnittenen Quelle (Screencapture mit Letterbox)."""
    import subprocess
    x, y, w, h = crop
    dst.parent.mkdir(parents=True, exist_ok=True)
    tt = max(0.0, t - 1.0 / (fps or 24))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{tt:.4f}", "-i", str(path), "-frames:v", "1",
                    "-vf", f"crop={w}:{h}:{x}:{y},scale={STILL_SIZE[0]}:{STILL_SIZE[1]}", str(dst)], check=True)
    return dst


# ---------- Rohschnitt ----------
def build_rough_cut(ep: Episode, templates_dir: Path, still_source: str | None = None, by_strand: bool = True,
                    with_stills: bool = True, speakers: set[str] | None = None, progress=lambda p: None) -> dict:
    scenes = ordered_scenes(ep, by_strand)
    tpl_file = templates_dir / "rohschnitt_vorlage.json"
    template = rough_cut.load_template(tpl_file if tpl_file.exists() else None)
    out_dir = ep.p.gl / "schnitt"
    version = rough_cut.next_version(out_dir)
    pr = ep.project()
    ref_src = ep.source(pr.reference_source) if pr.reference_source else None
    if ref_src is None:
        raise ValueError("Keine Referenz-Episode importiert (Quellen).")
    for sc in scenes:
        for i, g in enumerate(sc.segmente):
            if g.out <= g.in_:
                raise ValueError(f"Szene „{sc.titel or sc.id}“, Segment {i + 1}: Out liegt nicht nach In. Bitte korrigieren.")
            if ref_src.duration and g.out > ref_src.duration + 0.5:
                raise ValueError(f"Szene „{sc.titel or sc.id}“, Segment {i + 1}: liegt hinter dem Ende der Episode "
                                 f"({g.out:.1f} s > {ref_src.duration:.1f} s). Bitte im Szenen-Editor korrigieren.")
    pkg = rough_cut.build_package(
        scenes, slug=ep.p.slug, template=template, th=ep.settings.thresholds,
        alignment=load_alignment(ep), assets=load_assets(ep), maps=load_maps(ep), free_blocks=ep.free_blocks(),
        version=version, episode_fps=pr.fps, speaker_filter=speakers)
    ref = ep.source(pr.reference_source)
    rec_paths = {r["id"]: r["path"] for r in load_alignment(ep)["recordings"]}
    for tr in pkg["tracks"].values():
        for c in tr:
            if c["type"] == "comment" and c.get("rec"):
                c["rec_path"] = rec_paths.get(c["rec"], "")
    pkg["episode_file"] = ref.path
    pkg["stills_dir"] = "Videoelemente"
    still_info = None
    if with_stills:
        still_info = render_stills(ep, scenes, still_source, lambda p: progress(p * 0.8))
        pkg["stills_dir"] = Path(still_info["dir"]).name
    json_path = rough_cut.write_package(pkg, out_dir)
    xml_path = out_dir / f"schnitt_v{version}.xml"
    xml_path.write_text(fcpxml.to_fcpxml(pkg, ref.path, ref.duration, ep.p.root), encoding="utf-8")
    store.log_change(ep.p.gl, ep.settings.user, f"Rohschnitt v{version} erzeugt")
    progress(1.0)
    return {"version": version, "json": str(json_path), "xml": str(xml_path), "duration": pkg["duration"],
            "warnings": pkg["warnings"], "stills": still_info, "markers": len(pkg["markers"])}
