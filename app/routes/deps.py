from __future__ import annotations

import time
from datetime import timedelta

from fastapi import Depends, Header, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models import RequestNonce, Streamer, StreamerStatus
from app.security.hashing import hash_api_token, secrets_equal, sha256_hex
from app.security.validation import validate_nonce
from app.services.audit import utcnow


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request):
    factory = request.app.state.session_factory
    db: Session = factory()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def require_admin(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not x_admin_token or not secrets_equal(x_admin_token.strip(), settings.admin_api_token):
        raise AppError("unauthorized", "No autorizado", 401)


def require_streamer(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    authorization: str | None = Header(default=None),
) -> Streamer:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError("unauthorized", "Token inválido", 401)
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise AppError("unauthorized", "Token inválido", 401)
    digest = hash_api_token(token, settings.token_hash_pepper)
    streamer = db.query(Streamer).filter(Streamer.api_token_hash == digest).one_or_none()
    if streamer is None or streamer.status == StreamerStatus.REVOKED:
        raise AppError("unauthorized", "Token inválido", 401)
    if streamer.status != StreamerStatus.ACTIVE:
        raise AppError("streamer_suspended", "El acceso de este streamer está suspendido", 403)
    request.state.streamer = streamer
    return streamer


def require_fresh_request(
    request: Request,
    streamer: Streamer = Depends(require_streamer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    x_kb_timestamp: str | None = Header(default=None),
    x_kb_nonce: str | None = Header(default=None),
) -> Streamer:
    if not x_kb_timestamp or not x_kb_nonce:
        raise AppError("invalid_request", "Cabeceras de seguridad inválidas", 401)
    nonce = validate_nonce(x_kb_nonce)
    try:
        timestamp = int(x_kb_timestamp)
    except ValueError as exc:
        raise AppError("invalid_request", "Cabeceras de seguridad inválidas", 401) from exc
    now = int(time.time())
    if abs(now - timestamp) > settings.replay_window_seconds:
        raise AppError("replay_rejected", "La solicitud expiró", 401)
    db.query(RequestNonce).filter(RequestNonce.expires_at < utcnow()).delete(synchronize_session=False)
    digest = sha256_hex(f"{streamer.id}:{nonce}")
    db.add(
        RequestNonce(
            streamer_id=streamer.id,
            nonce_hash=digest,
            expires_at=utcnow() + timedelta(seconds=settings.replay_window_seconds * 2),
            created_at=utcnow(),
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("replay_rejected", "Solicitud repetida", 401) from exc
    return streamer
