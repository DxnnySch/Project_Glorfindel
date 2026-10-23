"""FastAPI-App: lokale REST-Schnittstelle + Auslieferung der Weboberfläche (nur localhost)."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import Settings
from .deps import AppState

WEB_DIR = Path(os.environ.get("GLORFINDEL_WEB", Path(__file__).resolve().parents[2] / "web"))
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "testserver"}


def create_app(state: AppState | None = None) -> FastAPI:
    state = state or AppState()
    app = FastAPI(title="Projekt Glorfindel", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.gl = state

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        """Schutz vor DNS-Rebinding und fremden Webseiten: nur localhost-Host, nur gleiche Herkunft bei Schreibzugriffen."""
        host = request.headers.get("host", "").rsplit(":", 1)[0] if not request.headers.get("host", "").startswith("[") \
            else request.headers.get("host", "").split("]")[0] + "]"
        if host not in LOCAL_HOSTS:
            return JSONResponse({"detail": "Nur lokaler Zugriff"}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            # Browser senden bei fremden Seiten immer Origin bzw. Sec-Fetch-Site; fehlt Origin, aber der Browser
            # meldet "cross-site/same-site", wird abgelehnt. Nicht-Browser-Clients (curl, Tests) bleiben möglich.
            if not origin and request.headers.get("sec-fetch-site", "none") in ("cross-site", "same-site"):
                return JSONResponse({"detail": "Fremde Herkunft abgelehnt"}, status_code=403)
            if origin:
                o_full = origin.split("://", 1)[-1]
                o = o_full.rsplit(":", 1)[0] if not o_full.startswith("[") else o_full.split("]")[0] + "]"
                h_full = request.headers.get("host", "")
                o_port, h_port = o_full.rsplit(":", 1)[-1] if o_full.count(":") and not o_full.endswith("]") else "", h_full.rsplit(":", 1)[-1] if h_full.count(":") and not h_full.endswith("]") else ""
                if o not in LOCAL_HOSTS or (o_port.isdigit() and h_port.isdigit() and o_port != h_port):
                    return JSONResponse({"detail": "Fremde Herkunft abgelehnt"}, status_code=403)
        return await call_next(request)

    from pydantic import ValidationError

    @app.exception_handler(FileNotFoundError)
    async def _nf(request: Request, exc: FileNotFoundError):
        return JSONResponse({"detail": str(exc) or "Datei nicht gefunden"}, status_code=404)

    @app.exception_handler(FileExistsError)
    async def _ex(request: Request, exc: FileExistsError):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def _val(request: Request, exc: ValueError):
        if isinstance(exc, ValidationError):
            msg = "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()[:3])
            return JSONResponse({"detail": f"Ungültige Eingabe – {msg}"}, status_code=400)
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.on_event("startup")
    def _maintenance() -> None:
        """Ältere Proxys im Hintergrund auf das Firefox-taugliche Format umstellen (sichtbar in der Aufgabenleiste)."""
        from . import maintenance
        if maintenance.old_proxies():
            state.jobs.submit("Proxys anpassen (Firefox-tauglicher Ton)", lambda progress: maintenance.fix_old_proxies(progress))

    from . import routes_core, routes_prod, routes_lib
    app.include_router(routes_core.router, prefix="/api")
    app.include_router(routes_prod.router, prefix="/api")
    app.include_router(routes_lib.router, prefix="/api")

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__}

    if WEB_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

        @app.get("/")
        def index():
            return FileResponse(WEB_DIR / "index.html")

        @app.get("/favicon.svg")
        def favicon():
            f = WEB_DIR / "favicon.svg"
            if not f.exists():
                raise HTTPException(404)
            return FileResponse(f)

    return app


def get_state(request: Request) -> AppState:
    return request.app.state.gl
