"""Routen: Word, Altformat-Import, Strang-Board, Aufnahme, Rohschnitt, Conform."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import conform as conform_mod
from . import detect, legacy_import, media, pipeline, script_docx, store
from .deps import AppState
from .models import Scene
from .routes_core import ep_of, st
from .service import Episode
from .timemap import TimeMap

router = APIRouter()


# ---------- Word ----------
@router.get("/ep/{season}/{episode}/script.docx")
def export_script(speaker: str | None = None, markers: bool = True, by_strand: bool = True,
                  ep: Episode = Depends(ep_of)):
    scenes = pipeline.ordered_scenes(ep, by_strand)
    out = ep.p.base / f"Skript {ep.p.slug}{'' if not speaker else ' ' + speaker}.docx"
    labels = {a["id"]: (a.get("title") or Path(a.get("path", "")).stem) for a in pipeline.load_assets(ep).values()}
    labels.update({m["id"]: m.get("titel", "") for m in pipeline.load_maps(ep).values()})
    script_docx.export_docx(scenes, out, title=f"{ep.p.slug} – {ep.project().title}".strip(" –"), speaker=speaker,
                            show_markers=markers, free_blocks=ep.free_blocks(), labels=labels)
    store.log_change(ep.p.gl, ep.settings.user, f"Word-Export ({speaker or 'alle'})")
    return FileResponse(out, filename=out.name,
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def _save_upload(f: UploadFile) -> Path:
    tmp = Path(tempfile.mkdtemp()) / (Path(f.filename or "skript.docx").name)
    tmp.write_bytes(f.file.read())
    return tmp


@router.post("/ep/{season}/{episode}/script/import-preview")
async def import_preview(file: UploadFile = File(...), ep: Episode = Depends(ep_of)):
    tmp = _save_upload(file)
    try:
        res = script_docx.import_docx(tmp)
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Die Datei ist kein gültiges Word-Dokument (.docx).")
    scenes = ep.scenes()
    probe = [Scene.model_validate(s.model_dump(by_alias=True)) for s in scenes]
    changed = script_docx.apply_import(probe, res)
    titles = {s.id: s.titel for s in scenes}
    return {"changed": changed, "changed_titles": [titles.get(c, c) for c in changed], "unknown": [s for s in res.scenes if s not in {x.id for x in scenes}],
            "free_blocks": res.free_blocks}


@router.post("/ep/{season}/{episode}/script/import")
async def import_apply(file: UploadFile = File(...), ep: Episode = Depends(ep_of)):
    tmp = _save_upload(file)
    try:
        res = script_docx.import_docx(tmp)
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Die Datei ist kein gültiges Word-Dokument (.docx).")
    scenes = ep.scenes()
    changed = script_docx.apply_import(scenes, res)
    for sc in scenes:
        if sc.id in changed:
            ep.save_scene(sc, f"Szene {sc.id} aus Word übernommen")
    old = {b.get("titel"): b for b in ep.free_blocks()}
    for b in res.free_blocks:  # Dauer überlebt den Word-Rundlauf
        if old.get(b.get("titel"), {}).get("dauer"):
            b["dauer"] = old[b["titel"]]["dauer"]
    if res.free_blocks:  # Dokument ohne Rahmenteile lässt die vorhandenen (samt Dauer) unangetastet
        ep.save_free_blocks(res.free_blocks)
    return {"changed": changed, "free_blocks": len(res.free_blocks)}


@router.post("/ep/{season}/{episode}/script/import-legacy")
async def import_legacy(file: UploadFile = File(...), replace: bool = False, ep: Episode = Depends(ep_of)):
    """Bestehendes Skript (Altformat mit [Szenen] und P:/D:) als neue Szenen übernehmen."""
    tmp = _save_upload(file)
    res = legacy_import.parse_legacy_script(tmp)
    if replace:
        for s in ep.scenes():
            ep.delete_scene(s.id)
    base = len(ep.scenes())
    for i, sc in enumerate(res["scenes"]):
        sc.id, sc.reihenfolge = ep.next_scene_id(), base + i
        ep.save_scene(sc, f"Szene {sc.id} aus Altformat importiert")
    ep.save_free_blocks(res["free_blocks"] if replace else ep.free_blocks() + res["free_blocks"])
    return res["stats"]


# ---------- Strang-Board ----------
class DetectBody(BaseModel):
    source: str = ""
    threshold: float = 27.0
    min_scene_s: float = 15.0


@router.post("/ep/{season}/{episode}/board/detect")
def board_detect(body: DetectBody, ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    def work(progress):
        sid = body.source or ep.project().reference_source
        progress.plan([("Proxy bereitstellen", 3), ("Bildschnitte erkennen", 10), ("Tonpausen erkennen", 3), ("Szenen vorschlagen", 1), ("Vorschaubilder erzeugen", 3), ("Speichern", 1)])
        progress.step(0, "Vorschauvideo (Proxy) prüfen")
        if ep.proxy_path(sid).exists():
            proxy = ep.proxy_path(sid)
        else:
            progress.detail("Proxy fehlt, wird zuerst erzeugt")
            proxy = ep.ensure_proxy(sid, on_progress=lambda f, info: progress.fraction(f, "Proxy: " + info["text"]))
        progress.step(1, "Inhaltsbasierte Schnitterkennung")
        shots = detect.detect_shots(proxy, body.threshold, on_progress=progress.fraction)
        progress.step(2, "Stille im Ton suchen")
        sil = detect.detect_silences(proxy, on_progress=progress.fraction)
        progress.step(3, f"{len(shots)} Schnitte und {len(sil)} Tonpausen zu Szenen bündeln")
        scenes = detect.propose_scenes(shots, sil, min_len=body.min_scene_s)
        progress.step(4, f"{len(scenes)} Vorschläge")
        ths = detect.thumbnails(proxy, [s["start"] for s in scenes], ep.p.cache() / "thumbs",
                                on_progress=lambda k, n: progress.sub(k, n, f"Vorschaubild {k + 1} von {n}", "Vorschaubilder"))
        for s, t in zip(scenes, ths):
            s["thumb"] = t.name
        progress.step(5)
        out = {"source": sid, "scenes": scenes, "shots": len(shots)}
        store.write_json(ep.p.cache() / "board.json", out)
        return out
    return {"job": state.jobs.submit("Szenenerkennung", work)}


@router.get("/ep/{season}/{episode}/board")
def board(ep: Episode = Depends(ep_of)):
    return store.read_json(ep.p.cache() / "board.json", {"scenes": []})


class BoardScene(BaseModel):
    start: float
    end: float
    thumb: str = ""
    strang: str = ""
    done: bool = False


class BoardBody(BaseModel):
    source: str = ""
    scenes: list[BoardScene]


@router.put("/ep/{season}/{episode}/board")
def save_board(body: BoardBody, ep: Episode = Depends(ep_of)):
    for s in body.scenes:
        if s.end <= s.start:
            raise HTTPException(400, f"Ende muss nach dem Anfang liegen ({s.start:.1f}–{s.end:.1f} s)")
    data = store.read_json(ep.p.cache() / "board.json", {})
    data.update(source=body.source or data.get("source", ""), scenes=[s.model_dump() for s in body.scenes])
    store.write_json(ep.p.cache() / "board.json", data)
    return {"ok": True}


@router.get("/ep/{season}/{episode}/thumb/{name}")
def thumb(name: str, ep: Episode = Depends(ep_of)):
    f = ep.p.cache() / "thumbs" / Path(name).name
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f)


@router.get("/ep/{season}/{episode}/frame")
def frame(source: str, t: float, w: int = 480, ep: Episode = Depends(ep_of)):
    """Einzelbild einer Quelle bei Episodenzeit t (für Filmstreifen, Doppelansicht)."""
    src = ep.source(source)
    tm = TimeMap(src.anchors) if src.role != "referenz" else TimeMap([])
    dst = ep.p.cache() / "frames" / f"{source}_{int(tm.ref_to_src(t) * 1000)}_{w}.jpg"
    if not dst.exists():
        proxy = ep.proxy_path(source)
        media.extract_frame(proxy if proxy.exists() else ep.source_path(src), tm.ref_to_src(t), dst, width=w)
    return FileResponse(dst)


class SceneFromRange(BaseModel):
    start: float
    end: float
    strang: str = ""
    titel: str = ""


@router.post("/ep/{season}/{episode}/board/create-scenes")
def board_create(body: list[SceneFromRange], ep: Episode = Depends(ep_of)):
    out = []
    for b in body:
        sc = ep.create_scene(strang=b.strang, titel=b.titel,
                             segmente=[{"in": b.start, "out": min(b.end, b.start + 9.5)}])
        out.append(sc.id)
    return {"created": out}


# ---------- Aufnahme ----------
class AddRecording(BaseModel):
    path: str
    speaker: str


@router.get("/ep/{season}/{episode}/recording")
def recording(ep: Episode = Depends(ep_of)):
    return pipeline.load_alignment(ep)


@router.post("/ep/{season}/{episode}/recording")
def add_recording(body: AddRecording, ep: Episode = Depends(ep_of)):
    if body.speaker not in ("philipp", "danny", "alle"):
        raise HTTPException(400, "Sprecher: philipp, danny oder alle")
    p = Path(body.path)
    if not (p if p.is_absolute() else Path(ep.p.root) / p).is_file():
        raise HTTPException(404, f"Aufnahme nicht gefunden: {body.path}")
    return pipeline.add_recording(ep, body.path, body.speaker)


@router.post("/ep/{season}/{episode}/recording/align")
def run_align(prefer: str = "last", ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    def work(progress):
        pipeline.run_alignment(ep, state.llm(), prefer, progress)
        return {"ok": True}
    return {"job": state.jobs.submit("Aufnahme-Abgleich", work)}


@router.get("/ep/{season}/{episode}/recording/{rid}/waveform")
def waveform(rid: str, ep: Episode = Depends(ep_of)):
    rec = next((r for r in pipeline.load_alignment(ep)["recordings"] if r["id"] == rid), None)
    if not rec:
        raise HTTPException(404)
    cache = ep.p.cache() / f"wave_{rid}.json"
    peaks = store.read_json(cache)
    if peaks is None:
        peaks = media.waveform_peaks(ep.p.root / rec["path"], buckets=3000)
        store.write_json(cache, peaks)
    return {"peaks": peaks, "duration": rec["duration"]}


@router.get("/ep/{season}/{episode}/recording/{rid}/audio")
def rec_audio(rid: str, ep: Episode = Depends(ep_of)):
    rec = next((r for r in pipeline.load_alignment(ep)["recordings"] if r["id"] == rid), None)
    if not rec:
        raise HTTPException(404)
    return FileResponse(ep.p.root / rec["path"])


class BlockTiming(BaseModel):
    scene: str
    block: int
    t_in: float
    t_out: float


@router.put("/ep/{season}/{episode}/recording/block")
def block_timing(body: BlockTiming, ep: Episode = Depends(ep_of)):
    return pipeline.set_block_timing(ep, body.scene, body.block, body.t_in, body.t_out)


class Adopt(BaseModel):
    scene: str
    block: int


@router.post("/ep/{season}/{episode}/recording/adopt")
def adopt(body: Adopt, ep: Episode = Depends(ep_of)):
    try:
        return pipeline.adopt_spoken_text(ep, body.scene, body.block).model_dump(by_alias=True)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------- Rohschnitt ----------
class BuildBody(BaseModel):
    still_source: str | None = None
    by_strand: bool = True
    with_stills: bool = True


@router.post("/ep/{season}/{episode}/rough-cut")
def build(body: BuildBody, ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    def work(progress):
        return pipeline.build_rough_cut(ep, state.templates_dir(), body.still_source, body.by_strand,
                                        body.with_stills, progress=progress)
    return {"job": state.jobs.submit("Rohschnitt erzeugen", work)}


@router.get("/ep/{season}/{episode}/rough-cut")
def versions(ep: Episode = Depends(ep_of)):
    d = ep.p.gl / "schnitt"
    return [{"version": int(f.stem.split("_v")[1]), "file": f.name, "xml": f.with_suffix(".xml").exists(),
             "modified": f.stat().st_mtime, "path": str(f)} for f in sorted(d.glob("schnitt_v*.json"))] if d.exists() else []


@router.get("/ep/{season}/{episode}/rough-cut/{version}/{kind}")
def download_cut(version: int, kind: str, ep: Episode = Depends(ep_of)):
    f = ep.p.gl / "schnitt" / f"schnitt_v{version}.{'xml' if kind == 'xml' else 'json'}"
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f, filename=f.name)


# ---------- Conform / Doppelansicht ----------
@router.get("/ep/{season}/{episode}/compare")
def compare(a: str, b: str, t: float, tb: float | None = None, ep: Episode = Depends(ep_of)):
    """Kontrollansicht: Frame aus Quelle a bei Episodenzeit t, aus b bei tb (Standard: über Zeitabbildung)."""
    sa, sb = ep.source(a), ep.source(b)
    tma = TimeMap(sa.anchors) if sa.role != "referenz" else TimeMap([])
    tmb = TimeMap(sb.anchors) if sb.role != "referenz" else TimeMap([])
    t_b = tmb.ref_to_src(t) if tb is None else tb
    pa, pb = ep.proxy_path(a), ep.proxy_path(b)
    res = conform_mod.compare_frames(pa if pa.exists() else ep.source_path(sa), tma.ref_to_src(t),
                                     pb if pb.exists() else ep.source_path(sb), t_b,
                                     ep.p.cache() / "compare", None if pa.exists() else sa.crop,
                                     None if pb.exists() else sb.crop)
    for k in ("a", "b", "diff"):
        if res.get(k):
            res[k] = f"/api/ep/{ep.season}/{ep.episode}/compare-img/{Path(res[k]).name}"
    return res


@router.get("/ep/{season}/{episode}/compare-img/{name}")
def compare_img(name: str, ep: Episode = Depends(ep_of)):
    f = ep.p.cache() / "compare" / Path(name).name
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f, headers={"Cache-Control": "no-store"})


def _scene_check(ep: Episode, source: str, progress=None) -> list[dict]:
    """Pro Szene Freeze Frame A/B (erster/letzter Segment-Frame) mit Korrelation Referenz vs. Quelle."""
    from .progress import as_progress
    pg = as_progress(progress)
    ref = ep.source(ep.project().reference_source)
    src = ep.source(source)
    tm = TimeMap(src.anchors)
    out = []
    pr, ps = ep.proxy_path(ref.id), ep.proxy_path(src.id)
    scenes = [s for s in pipeline.ordered_scenes(ep) if s.segmente]
    pg.plan([("Szenen vergleichen (Anfang und Ende je Segment)", 1)])
    pg.step(0)
    for k, sc in enumerate(scenes):
        pg.sub(k, len(scenes), f"Szene „{sc.titel or sc.id}“", "Szenen")
        pts = {"A": sc.segmente[0].in_ + 0.1, "B": sc.segmente[-1].out - 0.1}
        row = {"scene": sc.id, "titel": sc.titel}
        for name, t in pts.items():
            r = conform_mod.compare_frames(pr if pr.exists() else ep.source_path(ref), t,
                                           ps if ps.exists() else ep.source_path(src), tm.ref_to_src(t),
                                           ep.p.cache() / "check" / f"{sc.id}{name}",
                                           None if pr.exists() else ref.crop, None if ps.exists() else src.crop)
            row[name] = round(r["correlation"], 3) if r.get("correlation") is not None else None
        row["uncertain"] = any(row[k2] is None or row[k2] < 0.8 for k2 in ("A", "B"))
        out.append(row)
    pg.sub(len(scenes), len(scenes), "fertig", "Szenen")
    return out


@router.get("/ep/{season}/{episode}/scene-check")
def scene_check(source: str, ep: Episode = Depends(ep_of)):
    return _scene_check(ep, source)


@router.post("/ep/{season}/{episode}/scene-check")
def scene_check_job(source: str, ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    """Wie GET, aber als Hintergrundauftrag mit Fortschritt (Szene n von m)."""
    return {"job": state.jobs.submit("Szenenprüfung", lambda progress: _scene_check(ep, source, progress))}


class ConformBody(BaseModel):
    source: str
    codec: str = "prores"
    stills: bool = True


@router.post("/ep/{season}/{episode}/conform")
def run_conform(body: ConformBody, ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    if body.codec not in conform_mod.CODECS:
        raise HTTPException(400, f"Unbekanntes Format: {body.codec}")
    def work(progress):
        pr = ep.project()
        src, ref = ep.source(body.source), ep.source(pr.reference_source)
        progress.plan([("Zeitabbildung berechnen", 1), (f"HQ-Datei rendern ({body.codec})", 40), ("Standbilder aus der HQ-Datei", 6 if body.stills else 0.01)])
        progress.step(0, f"{len(src.anchors)} Ankerpunkte, Ziel-Länge {ref.duration:.0f} s")
        tm = TimeMap(src.anchors)
        base = (ep.p.base if state.settings.keep_hq_in_onedrive else ep.p.cache()) / "conform"
        progress.step(1, "ffmpeg startet …")
        dst = conform_mod.conform(ep.source_path(src), tm, ref.duration, base / f"{ep.p.slug.replace(' ', '_')}_HQ_conform",
                                  fps=ref.fps or pr.fps, codec=body.codec, progress_cb=lambda f, info: progress.fraction(f, info["text"]))
        info = {"file": str(dst)}
        progress.step(2, "Letztes Bild jeder Szene")
        if body.stills:
            info["stills"] = pipeline.render_stills(ep, pipeline.ordered_scenes(ep), body.source, progress)
        else:
            progress.skip(2, "abgeschaltet")
        return info
    return {"job": state.jobs.submit("HQ-Conform", work)}


# ---------- Rahmenteile (freie Blöcke) ----------
class FreeBlock(BaseModel):
    titel: str = ""
    text: str = ""
    after: str | None = None   # Szenen-ID, nach der der Block steht; None = am Anfang
    dauer: float | None = None  # bekannte Länge in Sekunden (z. B. Werbung 81 s)


@router.get("/ep/{season}/{episode}/free-blocks")
def get_free_blocks(ep: Episode = Depends(ep_of)):
    return ep.free_blocks()


@router.put("/ep/{season}/{episode}/free-blocks")
def put_free_blocks(body: list[FreeBlock], ep: Episode = Depends(ep_of)):
    ids = {s.id for s in ep.scenes()}
    for b in body:
        if b.after is not None and b.after not in ids:
            raise HTTPException(400, f"Unbekannte Szene: {b.after}")
        if b.dauer is not None and b.dauer < 0:
            raise HTTPException(400, "Dauer darf nicht negativ sein")
    ep.save_free_blocks([b.model_dump() for b in body])
    return {"ok": True}


# ---------- Take-Wahl ----------
class TakeBody(BaseModel):
    scene: str
    block: int
    take: int


@router.put("/ep/{season}/{episode}/recording/take")
def choose_take(body: TakeBody, ep: Episode = Depends(ep_of)):
    data = pipeline.load_alignment(ep)
    entry = next((b for b in data["scenes"].get(body.scene, []) if b["block"] == body.block), None)
    if not entry or not entry.get("takes") or not (0 <= body.take < len(entry["takes"])):
        raise HTTPException(404, "Take nicht gefunden")
    t = entry["takes"][body.take]
    entry.update({"in": round(max(0.0, t["start"] - 0.15), 3), "out": round(t["end"] + 0.30, 3), "chosen": body.take,
                  "confidence": round(t["score"] / 100.0, 3), "uncertain": t["score"] < 80.0, "manual": True})
    entry.pop("missing", None)
    pipeline.save_alignment(ep, data)
    return entry
