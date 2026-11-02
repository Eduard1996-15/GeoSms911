"""Punto de entrada de la API y del dashboard de GeoSms911."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import settings
from .db import init_db, purge_old_locations
from .events import bus
from .routers import alerts, auth, devices, geofences, ingest, messages, twilio_webhooks, ws
from .serializers import server_info

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("geosms911")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    bus.bind()
    try:
        deleted = purge_old_locations()
        if deleted:
            logger.info("Se eliminaron %s puntos de ubicacion vencidos", deleted)
    except Exception:  # pragma: no cover
        logger.exception("No se pudo limpiar el historial de ubicaciones")

    if settings.using_insecure_secret:
        logger.warning(
            "APP_SECRET inseguro. Define una clave aleatoria en .env antes de exponer el servidor."
        )
    if not settings.twilio_configured:
        logger.warning(
            "Twilio sin configurar: los SMS se registraran localmente pero NO se enviaran."
        )
    if settings.twilio_configured and settings.twilio_validate_signature:
        logger.info("Validacion de firma de Twilio activada (PUBLIC_BASE_URL=%s)", settings.public_base_url_clean)

    logger.info("GeoSms911 %s listo", __version__)
    yield


app = FastAPI(
    title="GeoSms911",
    description="Plataforma familiar de alertas, ubicacion y emergencias.",
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
    if request.url.path in {"/", "/a"} or request.url.path.startswith("/static/"):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' data: https://*.tile.openstreetmap.org https://tile.openstreetmap.org; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "connect-src 'self' ws: wss:; "
            "font-src 'self' data:; "
            "base-uri 'none'; form-action 'self';",
        )
    return response


app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(ingest.router)
app.include_router(alerts.router)
app.include_router(geofences.router)
app.include_router(messages.router)
app.include_router(twilio_webhooks.router)
app.include_router(ws.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def dashboard():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse(
        {"app": "GeoSms911", "dashboard": "no instalado", "docs": "/api/docs"}
    )


@app.get("/a", include_in_schema=False)
def open_app_page():
    """Pagina minima usada por los SMS de respaldo para abrir la app."""
    return HTMLResponse(
        """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Abrir GeoSms911</title>
  <style>
    body{font-family:system-ui,sans-serif;background:#0b1220;color:#e8eefc;
         display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
    main{text-align:center;padding:2rem;max-width:22rem}
    a{display:block;background:#e11d48;color:#fff;text-decoration:none;
      padding:1rem 1.5rem;border-radius:1rem;font-weight:700;margin-top:1.5rem}
    p{color:#9fb0cc;line-height:1.5}
  </style>
</head>
<body>
  <main>
    <h1>GeoSms911</h1>
    <p>Se recibio una orden de tu tutor. Abre la app para compartir tu ubicacion.</p>
    <a href="geosms911://open">Abrir GeoSms911</a>
  </main>
</body>
</html>"""
    )


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        **server_info(),
    }
