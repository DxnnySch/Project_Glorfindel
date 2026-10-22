"""Routen: Bildbibliothek, Assets, Karten, LLM-Funktionen."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import images, maps, media, pipeline
from .config import app_dir
from .deps import AppState
from .routes_core import ep_of, st
from .service import Episode

router = APIRouter()


def _index(state: AppState) -> images.ImageIndex:
    return images.ImageIndex(app_dir() / "image_index.db")


def _safe_under(root: Path, rel: str) -> Path:
    p = (root / rel).resolve()
    if root.resolve() not in p.parents and p != root.resolve():
        raise HTTPException(400, "Pfad außerhalb des OneDrive-Ordners")
    return p


# ---------- Bildindex ----------
@router.post("/images/index")
def index_images(state: AppState = Depends(st)):
    root = Path(state.settings.onedrive_root)

    def work(progress):
        idx = _index(state)
        total = {"added": 0, "unchanged": 0}
        for i, d in enumerate(state.settings.images_dirs):
            r = idx.index_folder(root, root / d)
            total["added"] += r["added"]
            total["unchanged"] += r["unchanged"]
            progress((i + 1) / len(state.settings.images_dirs))
        return total
    return {"job": state.jobs.submit("Bilder indizieren", work)}


@router.get("/images/search")
def search_images(q: str = "", tags: str = "", limit: int = 60, state: AppState = Depends(st)):
    return _index(state).search(q, [t for t in tags.split(",") if t], limit)


@router.get("/images/keywords")
def keywords(state: AppState = Depends(st)):
    return _index(state).all_keywords()[:200]


@router.get("/images/thumb")
def image_thumb(path: str, state: AppState = Depends(st)):
    root = Path(state.settings.onedrive_root)
    src = _safe_under(root, path)
    if not src.exists():
        raise HTTPException(404)
    dst = app_dir() / "thumbs" / (str(abs(hash(path))) + ".jpg")
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix.lower() in images.VIDEO_EXT:
            media.extract_frame(src, 0.5, dst, width=320)
        else:
            maps.thumbnail(src, dst, 320)
    return FileResponse(dst)


# ---------- Assets ----------
@router.get("/ep/{season}/{episode}/assets")
def get_assets(ep: Episode = Depends(ep_of)):
    return list(pipeline.load_assets(ep).values())


class NewAsset(BaseModel):
    path: str | None = None
    url: str | None = None


@router.post("/ep/{season}/{episode}/assets")
def add_asset(body: NewAsset, ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    """Bibliotheksbild oder Web-Bild als Asset anlegen (Credit + Konturfarbe vorbelegt)."""
    root = ep.p.root
    source_url = ""
    if body.url:
        try:
            r = images.web_import(body.url, ep.p.assets)
        except (ValueError, Exception) as e:  # noqa: BLE001
            raise HTTPException(400, f"Import fehlgeschlagen: {e}")
        file, source_url = r["path"], r["source_url"]
    elif body.path:
        file = _safe_under(root, body.path)
        if not file.exists():
            raise HTTPException(404, "Datei nicht gefunden")
    else:
        raise HTTPException(400, "path oder url angeben")
    from .paths import to_rel
    rel = to_rel(root, file)
    dup = next((a for a in pipeline.load_assets(ep).values() if a.get("path") == rel), None)
    if dup:
        return dup
    meta = _index(state).search_exact(rel) or images.read_xmp(file)
    artists = pipeline.store.read_json(_artists_file(state), {})
    data = {"path": rel, "source_url": source_url, "credit": images.default_credit(rel, meta, artists),
            "credit_link": "", "contour_color": images.contour_color(file), "zoom": True,
            "layout": "einzel", "title": (meta or {}).get("title", "")}
    return pipeline.save_asset(ep, data)


@router.put("/ep/{season}/{episode}/assets/{aid}")
def put_asset(aid: str, body: dict, ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    body["id"] = aid
    out = pipeline.save_asset(ep, body)
    # Künstler-Datenbank wächst über alle Folgen
    if body.get("credit") and body.get("path"):
        from .rough_cut import credit_from_filename
        key = credit_from_filename(body["path"])
        f = Path(state.settings.onedrive_root) / state.settings.templates_dir / "kuenstler.json"
        db = pipeline.store.read_json(_artists_file(state), {})
        if db.get(key) != body["credit"] and body["credit"] != key:
            db[key] = body["credit"]
            f.parent.mkdir(parents=True, exist_ok=True)
            pipeline.store.write_json(f, db)
    return out


@router.get("/ep/{season}/{episode}/asset-file")
def asset_file(path: str, ep: Episode = Depends(ep_of)):
    f = _safe_under(ep.p.root, path)
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f)


# ---------- Karten ----------
@router.get("/maps")
def get_maps(q: str = "", state: AppState = Depends(st)):
    folder = Path(state.settings.onedrive_root) / state.settings.maps_dir
    return maps.list_maps(folder, q)[:300] if folder.is_dir() else []


@router.get("/maps/thumb")
def map_thumb(path: str, state: AppState = Depends(st)):
    root = Path(state.settings.onedrive_root)
    src = _safe_under(root, path)
    if not src.exists():
        raise HTTPException(404)
    dst = app_dir() / "thumbs" / ("m" + str(abs(hash(path))) + ".jpg")
    return FileResponse(maps.thumbnail(src, dst, 600))


@router.get("/ep/{season}/{episode}/maps")
def ep_maps(ep: Episode = Depends(ep_of)):
    return list(pipeline.load_maps(ep).values())


@router.put("/ep/{season}/{episode}/maps/{mid}")
def put_map(mid: str, body: dict, ep: Episode = Depends(ep_of)):
    body["id"] = mid
    body.setdefault("elemente", [])
    return pipeline.save_map(ep, body)


@router.post("/ep/{season}/{episode}/maps/{mid}/render")
def render_map(mid: str, ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    m = pipeline.load_maps(ep).get(mid)
    if not m:
        raise HTTPException(404, "Karte unbekannt")
    img = _safe_under(ep.p.root, m["bild"])

    def work(progress):
        sheet = maps.render_sheet(m, img, ep.p.maps / f"{mid}_blatt.png")
        progress(0.3)
        clip = maps.render_placeholder_clip(m, img, ep.p.maps / f"{mid}_platzhalter.mp4")
        from .paths import to_rel
        m["placeholder_clip"] = to_rel(ep.p.root, clip)
        m["sheet"] = to_rel(ep.p.root, sheet)
        pipeline.save_map(ep, m)
        return {"sheet": str(sheet), "clip": str(clip)}
    return {"job": state.jobs.submit(f"Karte {mid} rendern", work)}


# ---------- LLM ----------
class TextBody(BaseModel):
    text: str


@router.get("/llm/status")
def llm_status(state: AppState = Depends(st)):
    l = state.llm()
    ok = bool(l.client)
    models = l.models() if ok else []
    return {"enabled": state.settings.llm.enabled, "key": ok, "models": models, "error": l.last_error,
            "features": state.settings.llm.features,
            "chosen": {f: l.model_for(f) for f in state.settings.llm.features} if models else {}}


@router.post("/llm/check-names")
def check_names(body: TextBody, state: AppState = Depends(st)):
    return state.llm().check_names(body.text)


@router.post("/llm/search-terms")
def search_terms(body: TextBody, state: AppState = Depends(st)):
    return state.llm().suggest_search_terms(body.text)


class MapSuggest(BaseModel):
    text: str


@router.post("/llm/suggest-map")
def suggest_map(body: MapSuggest, state: AppState = Depends(st)):
    folder = Path(state.settings.onedrive_root) / state.settings.maps_dir
    names = [m["name"] for m in maps.list_maps(folder)][:80] if folder.is_dir() else []
    return state.llm().suggest_map(body.text, names) or {}


@router.post("/llm/scene-title")
def scene_title(body: TextBody, state: AppState = Depends(st)):
    l = state.llm()
    return {"titel": l.scene_title(body.text) if l.enabled("scene_titles") else None}


@router.delete("/ep/{season}/{episode}/assets/{aid}")
def delete_asset(aid: str, ep: Episode = Depends(ep_of)):
    f = ep.p.assets / f"{Path(aid).name}.json"
    if not f.exists():
        raise HTTPException(404, "Bild unbekannt")
    users = [f"{s.titel or s.id}" for s in ep.scenes() for b in s.kommentar for a in b.anker if a.asset == aid]
    if users:
        raise HTTPException(409, f"Wird noch verwendet in: {', '.join(sorted(set(users)))}")
    f.unlink()
    pipeline.store.log_change(ep.p.gl, ep.settings.user, f"Asset {aid} entfernt")
    return {"ok": True}


def _artists_file(state: AppState) -> Path:
    """OneDrive-Datei (geteilt) hat Vorrang vor der mitgelieferten."""
    od = Path(state.settings.onedrive_root) / state.settings.templates_dir / "kuenstler.json"
    return od if od.exists() else state.templates_dir() / "kuenstler.json"


@router.get("/artists")
def get_artists(state: AppState = Depends(st)):
    return pipeline.store.read_json(_artists_file(state), {})


@router.put("/artists")
def put_artists(body: dict[str, str], state: AppState = Depends(st)):
    d = Path(state.settings.onedrive_root) / state.settings.templates_dir
    d.mkdir(parents=True, exist_ok=True)
    pipeline.store.write_json(d / "kuenstler.json", {k.strip().lower(): v.strip() for k, v in body.items() if k.strip() and v.strip()})
    return {"ok": True}
