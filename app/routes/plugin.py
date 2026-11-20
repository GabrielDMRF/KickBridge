from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.models import Streamer
from app.routes.deps import get_db, require_fresh_request
from app.schemas.api import ChatIn, LinkStartIn
from app.security.validation import normalize_uuid, validate_chat_content, validate_username

router = APIRouter(prefix="/v1", tags=["plugin"])


@router.post("/players/{minecraft_uuid}/link")
def start_link(
    minecraft_uuid: str,
    payload: LinkStartIn,
    request: Request,
    streamer: Streamer = Depends(require_fresh_request),
    db: Session = Depends(get_db),
) -> dict:
    uuid = normalize_uuid(minecraft_uuid)
    username = validate_username(payload.minecraft_username)
    url, expires_in = request.app.state.linking.start(db, streamer, uuid, username, payload.expiration_seconds)
    return {"url": url, "expires_in": expires_in}


@router.get("/players/{minecraft_uuid}")
def player_status(
    minecraft_uuid: str,
    request: Request,
    streamer: Streamer = Depends(require_fresh_request),
    db: Session = Depends(get_db),
) -> dict:
    return request.app.state.linking.status(db, streamer, normalize_uuid(minecraft_uuid))


@router.delete("/players/{minecraft_uuid}")
async def unlink_player(
    minecraft_uuid: str,
    request: Request,
    streamer: Streamer = Depends(require_fresh_request),
    db: Session = Depends(get_db),
) -> dict:
    await request.app.state.linking.unlink(db, streamer, normalize_uuid(minecraft_uuid))
    return {"unlinked": True}


@router.post("/players/{minecraft_uuid}/chat")
async def send_chat(
    minecraft_uuid: str,
    payload: ChatIn,
    request: Request,
    streamer: Streamer = Depends(require_fresh_request),
    db: Session = Depends(get_db),
) -> dict:
    content = validate_chat_content(payload.content)
    return await request.app.state.chat.send(db, streamer, normalize_uuid(minecraft_uuid), content)
