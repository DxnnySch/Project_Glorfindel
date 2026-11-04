"""Routen der Premiere-Bridge: WebSocket für das Panel, Status/Aufrufe für die Oberfläche."""
from __future__ import annotations

import hmac

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.requests import HTTPConnection

from . import panel_package, premiere_ops
from .config import app_dir
from .bridge import HUB, PROTOCOL, BridgeError, get_token
from .deps import AppState
from .routes_core import ep_of
from .service import Episode


def _origin_ok(origin: str | None) -> bool:
    """Webseiten (http/https) dürfen sich nie verbinden; das UXP-Panel sendet keinen Web-Origin."""
    if not origin:
        return True
    o = origin.lower()
    return not (o.startswith("http://") or o.startswith("https://"))


def require_local(request: HTTPConnection) -> None:
    """Zusätzlich zur App-Middleware: Host muss lokal sein (Schutz vor DNS-Rebinding); schreibende Aufrufe nur von gleicher Herkunft."""
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
    if host not in ("localhost", "127.0.0.1", "::1", "testserver"):
        raise HTTPException(403, "Nur lokaler Zugriff")
    origin = request.headers.get("origin")
    method = request.scope.get("method", "GET")
    if request.scope.get("type") == "http" and method not in ("GET", "HEAD", "OPTIONS") and origin:
        o = origin.split("://", 1)[-1].rsplit(":", 1)[0].strip("[]")
        if o not in ("localhost", "127.0.0.1", "::1"):
            raise HTTPException(403, "Fremde Herkunft abgelehnt")


router = APIRouter(dependencies=[Depends(require_local)])


def st(request: Request) -> AppState:
    return request.app.state.gl


@router.websocket("/bridge/ws")
async def bridge_ws(ws: WebSocket, token: str = ""):
    host = (ws.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
    if host not in ("localhost", "127.0.0.1", "::1", "testserver") or not _origin_ok(ws.headers.get("origin")) \
            or not hmac.compare_digest(token, get_token()):
        await ws.close(code=4403)
        return
    await ws.accept()
    await HUB.serve(ws)


@router.get("/bridge/pairing")
def pairing(request: Request):
    """Das Panel holt hier den Token. Fremde Webseiten können die Antwort nicht lesen (kein CORS)."""
    return {"token": get_token(), "protocol": PROTOCOL, "port": request.url.port}


@router.get("/bridge/status")
def status():
    return HUB.status()


class CallBody(BaseModel):
    op: str
    args: dict = {}
    timeout: float = 60


@router.post("/bridge/call")
def call(body: CallBody):
    """Einzelne Operation (nur lesende/Diagnose-Operationen über die Oberfläche; Bauen/Tauschen laufen als Jobs)."""
    if body.op not in ("ping", "info", "introspect", "selftest", "project.dump", "sequence.dump", "template.inspect", "probe.bin", "probe.place", "probe.swap", "probe.items"):
        raise HTTPException(400, "Diese Operation läuft nur als Auftrag.")
    try:
        return {"data": HUB.call(body.op, body.args, timeout=min(body.timeout, 300))}
    except BridgeError as e:
        raise HTTPException(409, str(e))


@router.get("/premiere/effects")
def premiere_effects(state: AppState = Depends(st)):
    """Wählbare Effekte für Artworks/Karten (aus den .prfpset-Vorgaben, sonst mitgelieferter Stand)."""
    s = state.settings
    lib = premiere_ops.library_for(Path(s.onedrive_root or "."), s.premiere.presets_dir, state.templates_dir())
    rows = [{"id": "drop_shadow", "name": "Schlagschatten", "quelle": "Ursprungsschnitt"}]
    rows += [{"id": k, "name": v.get("quelle", k).rsplit(".", 1)[0], "quelle": "Vorgabe"} for k, v in lib.items() if k not in ("zoom",)]
    return {"effekte": rows, "ordner": str(Path(s.onedrive_root or ".") / s.premiere.presets_dir)}


# ---------- Abläufe pro Folge ----------
@router.get("/ep/{season}/{episode}/premiere")
def premiere_state(ep: Episode = Depends(ep_of)):
    st = premiere_ops.load_state(ep)
    return {**st, "bridge": HUB.status()["connected"], "hq_vorhanden": bool(st.get("hq") and __import__("pathlib").Path(st["hq"]).exists()),
            "sync": premiere_ops.sync_state(ep)}


class BuildBody(BaseModel):
    by_strand: bool = True


@router.post("/ep/{season}/{episode}/premiere/build")
def premiere_build(body: BuildBody, ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    return {"job": state.jobs.submit("Rohschnitt in Premiere bauen", lambda progress: premiere_ops.build_in_premiere(
        ep, state.templates_dir(), progress, body.by_strand))}


class SwapBody(BaseModel):
    to: str   # "hq" | "proxy"


@router.post("/ep/{season}/{episode}/premiere/swap")
def premiere_swap(body: SwapBody, ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    if body.to not in ("hq", "proxy"):
        raise HTTPException(400, "to: hq oder proxy")
    return {"job": state.jobs.submit("Premiere auf HQ umstellen" if body.to == "hq" else "Premiere auf Proxy zurückstellen",
                                     lambda progress: premiere_ops.swap(ep, body.to, progress))}


class SyncBody(BaseModel):
    apply: bool = False


@router.post("/ep/{season}/{episode}/premiere/sync")
def premiere_sync_read(body: SyncBody, ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    """Änderungen an den Serienclips aus Premiere einlesen (apply=false: nur anzeigen, true: in die Segmente übernehmen)."""
    return {"job": state.jobs.submit("Änderungen aus Premiere übernehmen" if body.apply else "Änderungen in Premiere suchen",
                                     lambda progress: premiere_ops.read_from_premiere(ep, body.apply, progress))}


@router.post("/ep/{season}/{episode}/premiere/refresh-stills")
def premiere_refresh_stills(ep: Episode = Depends(ep_of), state: AppState = Depends(st)):
    return {"job": state.jobs.submit("Standbilder in Premiere aktualisieren", lambda progress: premiere_ops.refresh_stills(ep, progress))}


@router.post("/bridge/selftest")
def premiere_selftest(state: AppState = Depends(st)):
    return {"job": state.jobs.submit("Premiere-Selbsttest", lambda progress: premiere_ops.run_selftest(None, progress, templates_dir=state.templates_dir()))}


# ---------- Panel einrichten ----------
@router.get("/bridge/panel-info")
def panel_info():
    return {"installer": panel_package.installer_available(), "ordner": str(panel_package.PANEL_DIR)}


@router.get("/bridge/panel.ccx")
def panel_download():
    ccx = panel_package.build_ccx(app_dir() / "bridge" / "Glorfindel-Bridge.ccx")
    return FileResponse(ccx, filename=ccx.name, media_type="application/octet-stream")


@router.post("/bridge/install-panel")
def panel_install():
    """Paket bauen und den Creative-Cloud-Installer starten (nur auf Klick des Nutzers)."""
    ccx = panel_package.build_ccx(app_dir() / "bridge" / "Glorfindel-Bridge.ccx")
    return {**panel_package.install(ccx), "datei": str(ccx)}
