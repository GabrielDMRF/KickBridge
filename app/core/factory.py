from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.database.session import make_engine, make_session_factory
from app.routes import admin, health, oauth, plugin
from app.security.crypto import TokenCipher
from app.security.rate_limit import SlidingWindowLimiter
from app.services.chat import ChatService
from app.services.kick_client import KickClient, KickRequestError
from app.services.linking import LinkingService
from app.services.streamers import StreamerService

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    resolved.validate_runtime()
    configure_logging(resolved.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if getattr(app.state, "kick", None) is None:
            app.state.kick = KickClient(resolved)
            app.state.owns_kick = True
        else:
            app.state.owns_kick = False
        _wire_services(app, resolved)
        yield
        if app.state.owns_kick:
            await app.state.kick.aclose()

    app = FastAPI(
        title="KickBridge API",
        version="1.0.0",
        summary="Vincula cuentas de Kick y publica en el chat con la identidad OAuth de cada jugador.",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.settings = resolved
    app.state.engine = make_engine(resolved.database_url)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.state.ip_limiter = SlidingWindowLimiter()
    if getattr(app.state, "kick", None) is not None:
        _wire_services(app, resolved)

    app.include_router(health.router)
    app.include_router(oauth.router)
    app.include_router(plugin.router)
    app.include_router(admin.router)

    @app.get("/admin", include_in_schema=False)
    def admin_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "admin.html")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        if resolved.require_https and request.url.path not in {"/health", "/ready"}:
            scheme = request.url.scheme
            if resolved.trust_proxy:
                forwarded = request.headers.get("x-forwarded-proto", scheme)
                scheme = forwarded.split(",")[0].strip().lower()
            if scheme != "https":
                return JSONResponse(
                    status_code=400,
                    content={"error": {"code": "https_required", "message": "HTTPS es obligatorio"}},
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        headers = {}
        if exc.retry_after is not None:
            headers["Retry-After"] = str(exc.retry_after)
        return JSONResponse(status_code=exc.status_code, content=exc.body(), headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "invalid_request", "message": "La solicitud no es válida"}},
        )

    @app.exception_handler(KickRequestError)
    async def kick_handler(_request: Request, exc: KickRequestError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"error": {"code": "kick_unavailable", "message": "Kick no respondió correctamente", "kick_status": exc.status}},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_handler(_request: Request, _exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "conflict", "message": "El recurso ya existe"}},
        )

    return app


def _wire_services(app: FastAPI, settings: Settings) -> None:
    cipher = TokenCipher(settings.encryption_key_bytes)
    kick = app.state.kick
    app.state.cipher = cipher
    app.state.linking = LinkingService(settings, kick, cipher)
    app.state.chat = ChatService(settings, kick, cipher)
    app.state.streamers = StreamerService(settings)
