from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.models import StreamerStatus
from app.routes.deps import get_db, require_admin
from app.schemas.api import AccountOut, SlugIn, StatsOut, StreamerCreateIn, StreamerOut, StreamerUpdateIn
from app.security.validation import normalize_uuid, validate_slug

router = APIRouter(prefix="/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _out(streamer, linked: int, token: str | None = None) -> StreamerOut:
    return StreamerOut(
        id=streamer.id,
        name=streamer.name,
        kick_broadcaster_user_id=streamer.kick_broadcaster_user_id,
        status=streamer.status,
        created_at=streamer.created_at,
        linked_accounts=linked,
        api_token=token,
    )


@router.get("/streamers", response_model=list[StreamerOut])
def list_streamers(request: Request, db: Session = Depends(get_db)) -> list[StreamerOut]:
    return [_out(streamer, count) for streamer, count in request.app.state.streamers.list_all(db)]


@router.post("/streamers", response_model=StreamerOut, status_code=201)
def create_streamer(payload: StreamerCreateIn, request: Request, db: Session = Depends(get_db)) -> StreamerOut:
    streamer, token = request.app.state.streamers.create(db, payload.name, payload.kick_broadcaster_user_id)
    return _out(streamer, 0, token)


@router.patch("/streamers/{streamer_id}", response_model=StreamerOut)
def update_streamer(streamer_id: int, payload: StreamerUpdateIn, request: Request, db: Session = Depends(get_db)) -> StreamerOut:
    streamer = request.app.state.streamers.update(db, streamer_id, payload.name, payload.kick_broadcaster_user_id)
    return _out(streamer, len(request.app.state.streamers.accounts(db, streamer.id)))


@router.post("/streamers/{streamer_id}/rotate-token", response_model=StreamerOut)
def rotate_token(streamer_id: int, request: Request, db: Session = Depends(get_db)) -> StreamerOut:
    streamer, token = request.app.state.streamers.rotate_token(db, streamer_id)
    return _out(streamer, len(request.app.state.streamers.accounts(db, streamer.id)), token)


@router.post("/streamers/{streamer_id}/suspend", response_model=StreamerOut)
def suspend(streamer_id: int, request: Request, db: Session = Depends(get_db)) -> StreamerOut:
    streamer = request.app.state.streamers.set_status(db, streamer_id, StreamerStatus.SUSPENDED)
    return _out(streamer, len(request.app.state.streamers.accounts(db, streamer.id)))


@router.post("/streamers/{streamer_id}/activate", response_model=StreamerOut)
def activate(streamer_id: int, request: Request, db: Session = Depends(get_db)) -> StreamerOut:
    streamer = request.app.state.streamers.set_status(db, streamer_id, StreamerStatus.ACTIVE)
    return _out(streamer, len(request.app.state.streamers.accounts(db, streamer.id)))


@router.post("/streamers/{streamer_id}/revoke", response_model=StreamerOut)
def revoke(streamer_id: int, request: Request, db: Session = Depends(get_db)) -> StreamerOut:
    streamer = request.app.state.streamers.set_status(db, streamer_id, StreamerStatus.REVOKED)
    return _out(streamer, len(request.app.state.streamers.accounts(db, streamer.id)))


@router.get("/streamers/{streamer_id}/accounts", response_model=list[AccountOut])
def accounts(streamer_id: int, request: Request, db: Session = Depends(get_db)) -> list[AccountOut]:
    rows = request.app.state.streamers.accounts(db, streamer_id)
    return [
        AccountOut(
            minecraft_uuid=minecraft.uuid,
            minecraft_username=minecraft.username,
            kick_user_id=kick.kick_user_id,
            kick_username=kick.kick_username,
            status=kick.status,
            linked_at=kick.linked_at,
        )
        for minecraft, kick in rows
    ]


@router.delete("/streamers/{streamer_id}/accounts/{minecraft_uuid}")
async def admin_unlink(streamer_id: int, minecraft_uuid: str, request: Request, db: Session = Depends(get_db)) -> dict:
    streamer = request.app.state.streamers.get(db, streamer_id)
    await request.app.state.linking.unlink(db, streamer, normalize_uuid(minecraft_uuid))
    return {"unlinked": True}


@router.get("/streamers/{streamer_id}/stats", response_model=StatsOut)
def stats(streamer_id: int, request: Request, db: Session = Depends(get_db)) -> StatsOut:
    return StatsOut(**request.app.state.streamers.stats(db, streamer_id))


@router.get("/audit")
def audit_log(
    request: Request,
    db: Session = Depends(get_db),
    streamer_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    _ = request
    query = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if streamer_id is not None:
        query = query.where(AuditLog.streamer_id == streamer_id)
    rows = db.scalars(query).all()
    return [
        {
            "id": row.id,
            "streamer_id": row.streamer_id,
            "minecraft_uuid": row.minecraft_uuid,
            "action": row.action,
            "result": row.result,
            "detail": row.detail,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.post("/channels/resolve")
async def resolve_channel(payload: SlugIn, request: Request) -> dict:
    slug = validate_slug(payload.slug)
    broadcaster_user_id, found = await request.app.state.kick.resolve_channel_slug(slug)
    return {"broadcaster_user_id": broadcaster_user_id, "slug": found}
