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
def scenes_in_video(scenes: list[Scene]) -> list[Scene]:
    """Szenen sind Messeinheiten; nur solche mit Segment oder Kommentar kommen in Rohschnitt und Skript."""
    from .scenes import in_video
    return [s for s in scenes if in_video(s)]


def ordered_scenes(ep: Episode, by_strand: bool = True) -> list[Scene]:
    scenes = ep.scenes()
    if not by_strand:
        return scenes
    from .scenes import apply_ablauf
    return apply_ablauf(sort_scenes(scenes, ep.strands()), ep.project().ablauf)


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


def _fix_transcript_with_llm(tr: list[dict], llm, chunk: int = 120, on_chunk=None) -> list[dict]:
    """Eigennamen per LLM nachkorrigieren; nur wortweise 1:1 übernehmen, wenn die Wortzahl stimmt."""
    out = [dict(w) for w in tr]
    for i in range(0, len(out), chunk):
        if on_chunk:
            on_chunk(i // chunk, -(-len(out) // chunk))
        part = out[i:i + chunk]
        fixed = llm.fix_transcript(" ".join(w["w"] for w in part), align.TOLKIEN_GLOSSARY).split()
        if len(fixed) == len(part):
            for w, f in zip(part, fixed):
                w["w"] = f
    return out


def transcribe_recording(ep: Episode, rec: dict, llm=None, progress=None, names: tuple[str, str] | None = None) -> list[dict]:
    """Transkript aus dem Cache oder neu (Whisper/ScaDS), danach optional Eigennamen per KI korrigieren.
    `names`: Schrittnamen für „Transkribieren“ und „KI-Korrektur“, wenn der Aufrufer einen Plan hat."""
    from .progress import as_progress
    pg = as_progress(progress)
    t_name, k_name = names or (None, None)
    cache = ep.p.recording / f"transkript_{rec['id']}.json"
    tr = store.read_json(cache)
    dur = rec.get("duration") or 0
    if tr is not None:
        if t_name:
            pg.step(t_name, f"Transkript aus früherem Lauf übernommen ({len(tr)} Wörter)")
            pg.finish_step()
        if k_name:
            pg.skip(k_name, "bereits korrigiert")
        return tr
    if t_name:
        pg.step(t_name)
    path = ep.p.root / rec["path"]
    backend = stt.choose_backend(ep.settings.transcription)
    if backend == "keins":
        raise RuntimeError("Für die Transkription fehlt Whisper. Entweder lokal installieren (install-Skript, Option Whisper) "
                           "oder in den Einstellungen „ScaDS.AI Whisper“ wählen (sendet die Aufnahme an ScaDS.AI).")
    if not path.exists():
        raise FileNotFoundError(f"Aufnahme nicht gefunden: {rec['path']}")
    label = "Whisper (lokal)" if backend == "lokal" else "ScaDS.AI Whisper"
    pg.detail(f"{label}: Modell laden und Audio lesen …")

    def cb(f: float, detail: str | None = None) -> None:
        pg.fraction(f, f"{label}: {media.fmt_clock(f * dur)} von {media.fmt_clock(dur)} Audio erkannt" if dur else f"{label}: {f * 100:.0f} %")
    if backend == "scads":
        if llm is None or llm.client is None:
            raise RuntimeError("ScaDS-Transkription gewählt, aber kein API-Schlüssel (.env) gefunden")
        tr = stt.transcribe_remote(path, llm.client, progress_cb=cb)
    else:
        tr = align.transcribe(path, ep.settings.whisper_model, progress_cb=cb)
    if llm is not None and llm.enabled("transcript_fix"):
        if k_name:
            pg.step(k_name, "KI prüft Eigennamen im Transkript")
        tr = _fix_transcript_with_llm(tr, llm, on_chunk=lambda i, n: pg.sub(i, n, f"KI-Korrektur: Abschnitt {i + 1} von {n}", "Abschnitte"))
    elif k_name:
        pg.skip(k_name, "KI aus oder kein Schlüssel")
    store.write_json(cache, tr)
    return tr


def run_alignment(ep: Episode, llm=None, prefer: str = "last", progress=None,
                  transcripts: dict[str, list[dict]] | None = None) -> dict:
    """Transkribiert (falls nötig) und gleicht alle Aufnahmen mit dem Skript ab."""
    from .progress import as_progress
    pg = as_progress(progress)
    data = load_alignment(ep)
    scenes = ordered_scenes(ep)
    results: dict[str, list[dict]] = {}
    n = len(data["recordings"])
    plan = []
    for k, rec in enumerate(data["recordings"]):
        plan += [(f"Aufnahme {k + 1}/{n} ({rec['speaker']}): transkribieren", 12), (f"Aufnahme {k + 1}/{n}: Eigennamen per KI prüfen", 2), (f"Aufnahme {k + 1}/{n}: mit dem Skript abgleichen", 2)]
    plan += [("Szenenstatus aktualisieren", 1), ("Ergebnis speichern", 1)]
    pg.plan(plan)
    all_tr: dict[str, list[dict]] = {}
    for k, rec in enumerate(data["recordings"]):
        names = (plan[3 * k][0], plan[3 * k + 1][0])
        if (transcripts or {}).get(rec["id"]):
            tr = transcripts[rec["id"]]
            pg.step(names[0], "Transkript vorgegeben")
            pg.finish_step()
            pg.skip(names[1])
        else:
            tr = transcribe_recording(ep, rec, llm, pg, names)
        all_tr[rec["id"]] = tr
        pg.step(plan[3 * k + 2][0], f"{len(tr)} Wörter Transkript mit den Kommentarblöcken vergleichen")
        text_units, bullet_units = [], []
        for sc in scenes:
            for bi, blk in enumerate(sc.kommentar):
                if rec["speaker"] not in ("alle", blk.sprecher):
                    continue
                if blk.modus == "stichpunkte":
                    bullet_units.append((sc.id, bi, blk.stichpunkte))
                elif blk.text.strip():
                    text_units.append((sc.id, bi, blk.text))
        pg.detail(f"{len(text_units)} Textblöcke und {len(bullet_units)} Stichpunkt-Blöcke von {rec['speaker']}")
        parts = [align.align_recording(text_units, tr, rec["id"], prefer=prefer),
                 align_bullets.align_bullets(bullet_units, tr, rec["id"])]
        for part in parts:
            for sid, blocks in part.items():
                results.setdefault(sid, []).extend(blocks)
    # manuelle Korrekturen aus früheren Läufen erhalten
    for sid, blocks in data.get("scenes", {}).items():
        for old in blocks:
            if old.get("manual"):
                new = results.setdefault(sid, [])
                new[:] = [b for b in new if b["block"] != old["block"]] + [old]
    data["scenes"] = {sid: sorted(bl, key=lambda b: b["block"]) for sid, bl in results.items()}
    data["zusatz"] = zusatz_stuecke(data, all_tr, scenes)
    pg.step("Szenenstatus aktualisieren")
    for i, sc in enumerate(scenes):
        pg.sub(i, len(scenes), f"Szene „{sc.titel or sc.id}“", "Szenen")
        bl = data["scenes"].get(sc.id, [])
        if sc.kommentar and bl and all(not b.get("missing") for b in bl) and len(bl) == len(sc.kommentar):
            sc.status = "abgeglichen"
            ep.save_scene(sc, f"Szene {sc.id} abgeglichen")
    pg.step("Ergebnis speichern")
    save_alignment(ep, data)
    store.log_change(ep.p.gl, ep.settings.user, "Aufnahme-Abgleich ausgeführt")
    return data


def zusatz_stuecke(data: dict, transcripts: dict[str, list[dict]], scenes: list[Scene]) -> list[dict]:
    """Gesprochenes ohne Skriptblock (Begrüßung, Überleitungen, Schluss) je Aufnahme, in Aufnahme-Reihenfolge."""
    from .extras import find_extras
    texts = [b.text for sc in scenes for b in sc.kommentar if b.text.strip()] + \
            [" ".join(b.stichpunkte) for sc in scenes for b in sc.kommentar if b.modus == "stichpunkte" and b.stichpunkte]
    out = []
    for rec in data["recordings"]:
        tr = transcripts.get(rec["id"])
        if not tr:
            continue
        ivs = [(b["in"], b["out"], (sid, b["block"])) for sid, bl in data["scenes"].items() for b in bl
               if b.get("rec") == rec["id"] and not b.get("missing") and b.get("in") is not None and b.get("out") is not None]
        for x in find_extras(tr, ivs, texts):
            out.append({**x, "rec": rec["id"], "speaker": rec["speaker"]})
    return out


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
def still_times(scenes: list[Scene], fps: float = rough_cut.EPISODE_FPS) -> dict[str, float]:
    """Dateiname -> Episodenzeit des Standbild-Frames (letzter Frame bzw. erster, je Szene)."""
    from .scenes import still_plan
    out = {}
    k = 0
    for sc in scenes:
        for si in still_plan(sc):
            k += 1
            seg = sc.segmente[si]
            out[f"{k}.png"] = rough_cut.snap_ep(seg.out if sc.standbild == "ende" else seg.in_, fps)
    return out


def render_stills(ep: Episode, scenes: list[Scene], source_id: str | None = None, progress=None) -> dict:
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
    from .progress import as_progress
    pg = as_progress(progress)
    for i, (name, t) in enumerate(times.items()):
        pg.sub(i, len(times), f"Standbild {name} bei {media.fmt_clock(t)} aus {src.path.rsplit('/', 1)[-1]}", "Standbilder")
        done[name] = str(media.extract_still_last_frame(path, tm.ref_to_src(t), fps, out_dir / name, STILL_SIZE)
                         if src.crop is None else _crop_still(path, tm.ref_to_src(t), fps, out_dir / name, src.crop))
    pg.sub(len(times), len(times), "alle Standbilder fertig", "Standbilder")
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
def rough_cut_scenes(ep: Episode, by_strand: bool = True, audio_order: bool = False) -> list[Scene]:
    """Szenen im Rohschnitt in ihrer Reihenfolge; Standbilder und Paket müssen dieselbe Liste benutzen."""
    scenes = scenes_in_video(ordered_scenes(ep, by_strand))
    return rough_cut.order_by_audio(scenes, load_alignment(ep)) if audio_order else scenes



def build_rough_cut(ep: Episode, templates_dir: Path, still_source: str | None = None, by_strand: bool = True,
                    with_stills: bool = True, speakers: set[str] | None = None, progress=None, audio_order: bool = False) -> dict:
    from .progress import as_progress
    pg = as_progress(progress)
    pg.plan([("Szenen ordnen und prüfen", 1), ("Schnittpaket berechnen (Spuren, Marker, Credits)", 3), ("Standbilder erzeugen", 12 if with_stills else 0.01),
             ("Premiere-XML schreiben", 1), ("Speichern und protokollieren", 1)])
    pg.step(0, "Reihenfolge wie in der Aufnahme" if audio_order else "Reihenfolge nach Strängen" if by_strand else "Reihenfolge wie im Szenen-Editor")
    scenes = rough_cut_scenes(ep, by_strand, audio_order)
    tpl_file = templates_dir / "rohschnitt_vorlage.json"
    template = rough_cut.load_template(tpl_file if tpl_file.exists() else None)
    template["sequence"] = {**template["sequence"], "fps": ep.settings.premiere.sequence_fps}      # Bildrate der Hauptsequenz (Einstellungen → Premiere)
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
    pg.step(1, f"{len(scenes)} Szenen, {sum(len(s.kommentar) for s in scenes)} Kommentarblöcke")
    pkg = rough_cut.build_package(
        scenes, slug=ep.p.slug, template=template, th=ep.settings.thresholds,
        alignment=load_alignment(ep), assets=load_assets(ep), maps=load_maps(ep), free_blocks=ep.free_blocks(),
        version=version, episode_fps=pr.fps, speaker_filter=speakers, group_titles={g["id"]: g.get("titel", "") for g in pr.gruppen},
        audio_order=audio_order)
    ref = ep.source(pr.reference_source)
    rec_paths = {r["id"]: r["path"] for r in load_alignment(ep)["recordings"]}
    for tr in pkg["tracks"].values():
        for c in tr:
            if c["type"] == "comment" and c.get("rec"):
                c["rec_path"] = rec_paths.get(c["rec"], "")
    pkg["episode_file"] = ref.path
    pkg["stills_dir"] = "Videoelemente"
    still_info = None
    pg.step(2, "Letztes Bild jeder Szene als PNG")
    if with_stills:
        still_info = render_stills(ep, scenes, still_source, pg)
        pkg["stills_dir"] = Path(still_info["dir"]).name
    else:
        pg.skip(2, "abgeschaltet")
    pg.step(3, f"Version {version}")
    xml_path = out_dir / f"schnitt_v{version}.xml"
    xml_text = None
    try:
        xml_text = fcpxml.to_fcpxml(pkg, ref.path, ref.duration, ep.p.root, stills_base=ep.p.base)
    except ValueError as e:  # nie still scheitern: Paket bleibt nutzbar, Hinweis statt kaputter Datei
        pkg["warnings"].append(str(e))
    json_path = rough_cut.write_package(pkg, out_dir)
    if xml_text:
        xml_path.write_text(xml_text, encoding="utf-8")
    pg.step(4)
    store.log_change(ep.p.gl, ep.settings.user, f"Rohschnitt v{version} erzeugt")
    return {"version": version, "json": str(json_path), "xml": str(xml_path) if xml_text else None, "duration": pkg["duration"],
            "warnings": pkg["warnings"], "stills": still_info, "markers": len(pkg["markers"])}
