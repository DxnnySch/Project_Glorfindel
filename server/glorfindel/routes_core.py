"""Routen: Einstellungen, Dateibrowser, Folgen, Quellen, Szenen, Stränge, Sperren, Jobs."""
from __future__ import annotations

import os
import string
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import media, store
from .config import Settings
from .deps import AppState
from .models import Anchor, CommentBlock, Scene, Segment, Strand
from .scenes import episode_report, normalize_block, scene_report, validate_segments
from .service import Episode, list_episodes

router = APIRouter()


def st(request: Request) -> AppState:
    return request.app.state.gl


def ep_of(season: int, episode: int, state: AppState = Depends(st)) -> Episode:
    return state.episode(season, episode)


# ---------- Einstellungen ----------
@router.get("/settings")
def get_settings(state: AppState = Depends(st)):
    s = state.settings.model_dump()
    from .config import scads_credentials
    s["_scads_key_present"] = bool(scads_credentials()[0])
    s["_onedrive_ok"] = bool(s["onedrive_root"]) and Path(s["onedrive_root"]).is_dir()
    return s


@router.put("/settings")
def put_settings(new: Settings, state: AppState = Depends(st)):
    state.settings = new
    state.save()
    return {"ok": True}


@router.get("/detect-onedrive")
def detect_onedrive():
    """Typische OneDrive-Stammordner vorschlagen (Windows/macOS)."""
    cands = []
    home = Path.home()
    for k in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        v = os.environ.get(k)
        if v:
            cands.append(v)
    cands += [str(p) for p in home.glob("OneDrive*")]
    cands += [str(p) for p in (home / "Library/CloudStorage").glob("OneDrive*")] if sys.platform == "darwin" else []
    if sys.platform == "win32":
        cands += [f"{d}:\\OneDrive" for d in string.ascii_uppercase if Path(f"{d}:\\OneDrive").is_dir()]
    seen, out = set(), []
    for c in cands:
        if c not in seen and Path(c).is_dir():
            seen.add(c)
            out.append(c)
    return out


@router.get("/fs")
def browse(path: str = "", files: bool = False):
    """Einfacher Dateibrowser für die Ordner-/Dateiauswahl (nur lokal)."""
    if not path:
        roots = ([f"{d}:\\" for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
                 if sys.platform == "win32" else ["/", str(Path.home())])
        return {"path": "", "parent": None, "entries": [{"name": r, "dir": True, "path": r} for r in roots]}
    p = Path(path)
    if not p.is_dir():
        raise HTTPException(404, "Ordner nicht gefunden")
    entries = []
    try:
        for c in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if c.name.startswith("."):
                continue
            if c.is_dir() or files:
                entries.append({"name": c.name, "dir": c.is_dir(), "path": str(c)})
    except PermissionError:
        raise HTTPException(403, "Kein Zugriff")
    return {"path": str(p), "parent": str(p.parent) if p.parent != p else "", "entries": entries[:500]}


@router.get("/system")
def system_check():
    import importlib.util
    import shutil
    from .stt import choose_backend
    return {"ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe")),
            "whisper": importlib.util.find_spec("faster_whisper") is not None,
            "transcription_backend": choose_backend("auto")}


REPO = "dxnnysch/project_glorfindel"


def _ver_tuple(v: str) -> tuple:
    import re
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


@router.get("/update")
def update_check():
    """Neuere Version auf GitHub? Schlägt still fehl (offline, privates Repo, kein Release)."""
    import httpx
    from . import __version__
    out = {"current": __version__, "latest": None, "newer": False, "url": f"https://github.com/{REPO}/releases"}
    try:
        r = httpx.get(f"https://api.github.com/repos/{REPO}/releases/latest", timeout=3.0, headers={"Accept": "application/vnd.github+json"})
        if r.status_code == 200:
            d = r.json()
            out.update(latest=d.get("tag_name"), url=d.get("html_url", out["url"]), notes=(d.get("body") or "")[:600])
            out["newer"] = _ver_tuple(d.get("tag_name", "0")) > _ver_tuple(__version__)
    except Exception:  # noqa: BLE001
        pass
    return out


# ---------- Jobs ----------
@router.get("/jobs")
def jobs_list(state: AppState = Depends(st)):
    return state.jobs.list()


@router.post("/jobs/{jid}/cancel")
def job_cancel(jid: str, state: AppState = Depends(st)):
    return state.jobs.cancel(jid)


@router.get("/jobs/{jid}")
def job(jid: str, state: AppState = Depends(st)):
    return state.jobs.get(jid)


# ---------- Folgen ----------
class NewEpisode(BaseModel):
    season: int
    episode: int
    title: str = ""
    fps: float = 23.976


@router.get("/episodes")
def episodes(state: AppState = Depends(st)):
    if not state.settings.onedrive_root:
        return []
    return list_episodes(state.settings)


@router.post("/episodes")
def create_episode(body: NewEpisode, state: AppState = Depends(st)):
    if not state.settings.onedrive_root or not Path(state.settings.onedrive_root).is_dir():
        raise HTTPException(409, "OneDrive-Stammordner ist nicht gesetzt (Einstellungen).")
    Episode.create(state.settings, body.season, body.episode, body.title, body.fps)
    return {"ok": True}


@router.get("/ep/{season}/{episode}")
def episode_overview(ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    sc = ep.scenes()
    return {"project": ep.project().model_dump(), "sources": [s.model_dump() for s in ep.sources()],
            "strands": [s.model_dump() for s in ep.strands()], "scenes": [s.model_dump(by_alias=True) for s in sc],
            "report": episode_report(sc, state.settings.thresholds),
            "conflicts": store.find_conflicts(ep.p.scenes), "free_blocks": ep.free_blocks()}


@router.get("/ep/{season}/{episode}/version")
def version(ep: Episode = Depends(ep_of)):
    """Änderungsmarke für Live-Nachladen (Änderungen anderer über OneDrive)."""
    latest = 0.0
    for f in list(ep.p.gl.rglob("*.json")):
        try:
            latest = max(latest, f.stat().st_mtime)
        except OSError:
            pass
    return {"version": latest}


@router.get("/ep/{season}/{episode}/log")
def change_log(limit: int = 100, ep: Episode = Depends(ep_of)):
    import json
    f = ep.p.gl / "log.jsonl"
    lines = f.read_text(encoding="utf-8").splitlines()[-limit:] if f.exists() else []
    return [json.loads(l) for l in reversed(lines) if l.strip()]


class ProjectPatch(BaseModel):
    title: str | None = None
    fps: float | None = None


@router.patch("/ep/{season}/{episode}/project")
def patch_project(body: ProjectPatch, ep: Episode = Depends(ep_of)):
    pr = ep.project()
    if body.title is not None:
        pr.title = body.title
    if body.fps is not None:
        pr.fps = body.fps
    ep.save_project(pr)
    return pr.model_dump()


# ---------- Quellen ----------
class ImportSource(BaseModel):
    path: str
    role: str = "screener"


@router.post("/ep/{season}/{episode}/sources")
def import_source(body: ImportSource, ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    p = Path(body.path)
    if not (p if p.is_absolute() else Path(ep.p.root) / p).is_file():
        raise HTTPException(404, f"Datei nicht gefunden: {body.path}")
    def work(progress):
        s = ep.import_source(body.path, body.role, wait=True)
        if not ep.proxy_path(s.id).exists():
            state.jobs.submit(f"Proxy {s.id} ({Path(s.path).name})", lambda progress, sid=s.id: str(ep.ensure_proxy(sid)))
        return s.model_dump()
    return {"job": state.jobs.submit("Quelle importieren", work)}


@router.post("/ep/{season}/{episode}/sources/{sid}/proxy")
def make_proxy(sid: str, ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    def work(progress):
        return str(ep.ensure_proxy(sid))
    return {"job": state.jobs.submit(f"Proxy {sid}", work)}


@router.get("/ep/{season}/{episode}/sources/{sid}/proxy-status")
def proxy_status(sid: str, ep: Episode = Depends(ep_of)):
    return {"ready": ep.proxy_path(sid).exists()}


@router.get("/ep/{season}/{episode}/media/{sid}")
def stream_proxy(sid: str, ep: Episode = Depends(ep_of)):
    f = ep.proxy_path(sid)
    if not f.exists():
        raise HTTPException(404, "Proxy fehlt – zuerst erzeugen")
    return FileResponse(f, media_type="video/mp4")


class AnchorsBody(BaseModel):
    anchors: list[Anchor]


@router.put("/ep/{season}/{episode}/sources/{sid}/anchors")
def set_anchors(sid: str, body: AnchorsBody, ep: Episode = Depends(ep_of)):
    return ep.set_anchors(sid, body.anchors).model_dump()


class SourcePatch(BaseModel):
    role: str | None = None
    crop: list[int] | None = None
    normalize_fps: float | None = None
    clear_crop: bool = False


@router.patch("/ep/{season}/{episode}/sources/{sid}")
def patch_source(sid: str, body: SourcePatch, ep: Episode = Depends(ep_of)):
    srcs = ep.sources()
    for s in srcs:
        if s.id == sid:
            if body.role:
                s.role = body.role  # type: ignore[assignment]
            if body.clear_crop:
                s.crop = None
            elif body.crop is not None:
                s.crop = body.crop
            if body.normalize_fps is not None:
                s.normalize_fps = body.normalize_fps
            ep._save_sources(srcs)
            ep.proxy_path(sid).unlink(missing_ok=True)  # Proxy neu erzeugen
            return s.model_dump()
    raise HTTPException(404, "Quelle unbekannt")


@router.post("/ep/{season}/{episode}/sources/{sid}/detect-crop")
def detect_crop(sid: str, ep: Episode = Depends(ep_of)):
    return {"crop": media.detect_crop(ep.source_path(ep.source(sid)))}


# ---------- Szenen ----------
def _ref_duration(ep: Episode) -> float:
    try:
        return ep.source(ep.project().reference_source).duration
    except Exception:  # noqa: BLE001
        return 0.0


@router.get("/ep/{season}/{episode}/scenes")
def scenes(ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    th = state.settings.thresholds
    from . import pipeline
    out_no = {x.id: i + 1 for i, x in enumerate(pipeline.ordered_scenes(ep, True))}
    return [{**s.model_dump(by_alias=True), "ausgabe": out_no.get(s.id), "report": scene_report(s, th),
             "lock": store.lock_status(ep.p.locks, s.id), "problems": validate_segments(s, _ref_duration(ep))} for s in ep.scenes()]


@router.post("/ep/{season}/{episode}/scenes")
def create_scene(body: dict, ep: Episode = Depends(ep_of)):
    body = {k: v for k, v in body.items() if k in {"titel", "strang", "segmente", "kommentar", "standbild"}}
    try:
        sc = ep.create_scene(**body)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Ungültige Szene: {e}")
    for b in sc.kommentar:
        normalize_block(b)
    return ep.save_scene(sc).model_dump(by_alias=True)


def _signature(s: Scene) -> tuple:
    """Inhalt, der den Abgleich mit der Aufnahme ungültig macht (Text, Sprecher, Segmente)."""
    return (tuple((b.sprecher, b.modus, b.text.strip(), tuple(b.stichpunkte)) for b in s.kommentar),
            tuple((round(g.in_, 3), round(g.out, 3)) for g in s.segmente))


@router.put("/ep/{season}/{episode}/scenes/{sid}")
def put_scene(sid: str, sc: Scene, base: str | None = None, ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    if sc.id != sid:
        raise HTTPException(400, "ID passt nicht")
    lock = store.lock_status(ep.p.locks, sid)
    for b in sc.kommentar:
        normalize_block(b)
    old = next((s for s in ep.scenes() if s.id == sid), None)
    if base and old and old.geaendert_am and old.geaendert_am > base and old.geaendert_von != state.settings.user:
        raise HTTPException(409, f"{old.geaendert_von} hat diese Szene inzwischen geändert.")
    if old and sc.status in ("aufgenommen", "abgeglichen") and old.status == sc.status and _signature(old) != _signature(sc):
        sc.status = "veraltet"
    ep.save_scene(sc)
    return {"scene": sc.model_dump(by_alias=True), "report": scene_report(sc, state.settings.thresholds),
            "problems": validate_segments(sc, _ref_duration(ep)),
            "locked_by_other": lock["user"] if lock and lock["user"] != state.settings.user else None}


@router.delete("/ep/{season}/{episode}/scenes/{sid}")
def delete_scene(sid: str, ep: Episode = Depends(ep_of)):
    ep.delete_scene(sid)
    return {"ok": True}


class Reorder(BaseModel):
    order: list[str]


@router.post("/ep/{season}/{episode}/scenes/{sid}/restore")
def restore_scene(sid: str, ep: Episode = Depends(ep_of)):
    return ep.restore_scene(sid).model_dump(by_alias=True)


@router.post("/ep/{season}/{episode}/scenes-reorder")
def reorder(body: Reorder, ep: Episode = Depends(ep_of)):
    ep.renumber(body.order)
    return {"ok": True}


@router.post("/ep/{season}/{episode}/scenes/{sid}/lock")
def lock(sid: str, ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    return store.acquire_lock(ep.p.locks, sid, state.settings.user)


@router.delete("/ep/{season}/{episode}/scenes/{sid}/lock")
def unlock(sid: str, ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    store.release_lock(ep.p.locks, sid, state.settings.user)
    return {"ok": True}


@router.get("/ep/{season}/{episode}/conflicts")
def conflicts(ep: Episode = Depends(ep_of)):
    """OneDrive-Konfliktkopien beider Versionen zum Zusammenführen anzeigen."""
    out = []
    for c in store.find_conflicts(ep.p.scenes):
        out.append({**c, "a": store.read_json(Path(c["original"])), "b": store.read_json(Path(c["copy"]))})
    return out


class Resolve(BaseModel):
    original: str
    other: str
    keep: str  # "original" | "copy"


@router.post("/ep/{season}/{episode}/conflicts/resolve")
def resolve_conflict(body: Resolve, ep: Episode = Depends(ep_of)):
    orig, copy = Path(body.original), Path(body.other)
    if ep.p.scenes not in orig.parents or ep.p.scenes not in copy.parents:
        raise HTTPException(400, "Pfad außerhalb des Szenenordners")
    if body.keep == "copy":
        store.write_json(orig, store.read_json(copy))
    copy.unlink(missing_ok=True)
    store.log_change(ep.p.gl, ep.settings.user, f"Konflikt {orig.name} gelöst ({body.keep})")
    return {"ok": True}


# ---------- Stränge ----------
@router.get("/ep/{season}/{episode}/strands")
def strands(ep: Episode = Depends(ep_of)):
    return [s.model_dump() for s in ep.strands()]


@router.put("/ep/{season}/{episode}/strands")
def put_strands(body: list[Strand], ep: Episode = Depends(ep_of)):
    ep.save_strands(body)
    return {"ok": True}


# ---------- Cockpit ----------
@router.get("/ep/{season}/{episode}/cockpit")
def cockpit(ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    """„Als Nächstes“-Liste: was fehlt noch, wohin muss man klicken."""
    from . import pipeline
    scs, srcs = ep.scenes(), ep.sources()
    al = pipeline.load_alignment(ep)
    assets = list(pipeline.load_assets(ep).values())
    tasks = []

    def add(n, text, view, scene=None):
        if n:
            tasks.append({"n": n, "text": text, "view": view, "scene": scene})
    add(0 if srcs else 1, "Referenz-Episode importieren", "sources")
    no_seg = [s for s in scs if not s.segmente]
    add(len(no_seg), "Szene(n) ohne Serienmaterial (Segment)", "editor", no_seg[0].id if no_seg else None)
    no_strand = [s for s in scs if not s.strang]
    add(len(no_strand), "Szene(n) ohne Strang", "editor", no_strand[0].id if no_strand else None)
    no_text = [s for s in scs if not any((b.text.strip() or b.stichpunkte) for b in s.kommentar)]
    add(len(no_text), "Szene(n) ohne Kommentartext", "editor", no_text[0].id if no_text else None)
    stale = [s for s in scs if s.status == "veraltet"]
    add(len(stale), "Szene(n) veraltet – Text oder Segmente wurden nach der Aufnahme geändert", "recording", stale[0].id if stale else None)
    add(sum(1 for a in assets if not (a.get("credit") or "").strip()), "Bild(er) ohne Credit", "images")
    red = [s for s in scs if scene_report(s, state.settings.thresholds)["light"] == "rot"]
    add(len(red), "Szene(n) mit zu langem Segment", "editor", red[0].id if red else None)
    if scs and al["recordings"]:
        pending = [s for s in scs if s.status not in ("abgeglichen",) and any(b.text.strip() or b.stichpunkte for b in s.kommentar)]
        add(len(pending), "Szene(n) noch nicht mit der Aufnahme abgeglichen", "recording", pending[0].id if pending else None)
    elif scs:
        add(1, "Sprachaufnahme importieren und abgleichen", "recording")
    phases = {
        "vorbereiten": bool(srcs), "skript": bool(scs) and not no_seg and not no_text,
        "einsprechen": bool(al["recordings"]) and bool(scs) and all(s.status == "abgeglichen" for s in scs if any(b.text.strip() or b.stichpunkte for b in s.kommentar)),
        "rohschnitt": (ep.p.gl / "schnitt").exists() and any((ep.p.gl / "schnitt").glob("schnitt_v*.json")),
    }
    return {"tasks": tasks, "phases": phases, "stale": [s.id for s in stale]}
