"""Routen der Premiere-Bridge: WebSocket für das Panel, Status/Aufrufe für die Oberfläche."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from pydantic import BaseModel
from starlette.requests import HTTPConnection

from .bridge import HUB, PROTOCOL, BridgeError, get_token
from .deps import AppState


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
    if body.op not in ("ping", "info", "introspect", "selftest", "project.dump", "sequence.dump", "template.inspect"):
        raise HTTPException(400, "Diese Operation läuft nur als Auftrag.")
    try:
        return {"data": HUB.call(body.op, body.args, timeout=min(body.timeout, 300))}
    except BridgeError as e:
        raise HTTPException(409, str(e))
