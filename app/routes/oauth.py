from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.routes.deps import get_db, get_settings
from app.security.rate_limit import SlidingWindowLimiter
from app.security.validation import validate_link_code
from app.services.linking import render_page

router = APIRouter(prefix="/v1/oauth", tags=["oauth"])


def _limiter(request: Request) -> SlidingWindowLimiter:
    return request.app.state.ip_limiter


def _client_ip(request: Request) -> str:
    settings = request.app.state.settings
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@router.get("/start/{code}")
def start_oauth(code: str, request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    settings = get_settings(request)
    if not _limiter(request).allow(f"oauth-start:{_client_ip(request)}", settings.oauth_ip_rate_limit, settings.oauth_ip_rate_window_seconds):
        raise AppError("rate_limited", "Demasiadas solicitudes", 429)
    safe_code = validate_link_code(code)
    location = request.app.state.linking.authorization_redirect(db, safe_code)
    parsed = urlparse(location)
    oauth_host = urlparse(settings.kick_oauth_base).netloc
    if parsed.scheme != "https" or parsed.netloc != oauth_host or not parsed.path.endswith("/oauth/authorize"):
        raise AppError("oauth_failed", "No se pudo iniciar la autorización", 500)
    response = RedirectResponse(location, status_code=302)
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/callback", response_class=HTMLResponse)
async def oauth_callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> HTMLResponse:
    settings = get_settings(request)
    if not _limiter(request).allow(f"oauth-callback:{_client_ip(request)}", settings.oauth_ip_rate_limit, settings.oauth_ip_rate_window_seconds):
        return HTMLResponse(render_page("Demasiadas solicitudes", "Espera un momento y vuelve a intentarlo."), status_code=429)
    if code and len(code) > 512:
        return HTMLResponse(render_page("Vinculación rechazada", "La respuesta de autorización no es válida."), status_code=400)
    if state and len(state) > 256:
        return HTMLResponse(render_page("Vinculación rechazada", "La respuesta de autorización no es válida."), status_code=400)
    page = await request.app.state.linking.complete(db, state, code, error)
    return HTMLResponse(page, headers={"Referrer-Policy": "no-referrer", "Cache-Control": "no-store"})
