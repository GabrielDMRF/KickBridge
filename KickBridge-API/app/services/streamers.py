from __future__ import annotations

import re
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models import KickAccount, MessageEvent, MinecraftAccount, Streamer, StreamerStatus
from app.security.hashing import generate_api_token, hash_api_token
from app.services.audit import audit, utcnow

NAME_RE = re.compile(r"[\w .'\-]{1,64}", re.UNICODE)


class StreamerService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create(self, db: Session, name: str, broadcaster_user_id: int) -> tuple[Streamer, str]:
        cleaned = _name(name)
        token = generate_api_token()
        now = utcnow()
        streamer = Streamer(
            name=cleaned,
            kick_broadcaster_user_id=broadcaster_user_id,
            api_token_hash=hash_api_token(token, self.settings.token_hash_pepper),
            status=StreamerStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        db.add(streamer)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise AppError("conflict", "Ya existe un streamer con ese nombre", 409) from exc
        audit(db, action="streamer.create", result="success", streamer_id=streamer.id, detail=cleaned)
        db.commit()
        return streamer, token

    def list_all(self, db: Session) -> list[tuple[Streamer, int]]:
        counts = dict(
            db.execute(
                select(MinecraftAccount.streamer_id, func.count(KickAccount.id))
                .join(KickAccount, KickAccount.minecraft_account_id == MinecraftAccount.id)
                .group_by(MinecraftAccount.streamer_id)
            ).all()
        )
        streamers = db.scalars(select(Streamer).order_by(Streamer.id)).all()
        return [(streamer, int(counts.get(streamer.id, 0))) for streamer in streamers]

    def get(self, db: Session, streamer_id: int) -> Streamer:
        streamer = db.get(Streamer, streamer_id)
        if streamer is None:
            raise AppError("not_found", "Streamer no encontrado", 404)
        return streamer

    def update(self, db: Session, streamer_id: int, name: str | None, broadcaster_user_id: int | None) -> Streamer:
        streamer = self.get(db, streamer_id)
        if name is not None:
            streamer.name = _name(name)
        if broadcaster_user_id is not None:
            streamer.kick_broadcaster_user_id = broadcaster_user_id
        streamer.updated_at = utcnow()
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise AppError("conflict", "Ya existe un streamer con ese nombre", 409) from exc
        audit(db, action="streamer.update", result="success", streamer_id=streamer.id)
        db.commit()
        return streamer

    def rotate_token(self, db: Session, streamer_id: int) -> tuple[Streamer, str]:
        streamer = self.get(db, streamer_id)
        if streamer.status == StreamerStatus.REVOKED:
            streamer.status = StreamerStatus.ACTIVE
        token = generate_api_token()
        streamer.api_token_hash = hash_api_token(token, self.settings.token_hash_pepper)
        streamer.updated_at = utcnow()
        audit(db, action="streamer.rotate_token", result="success", streamer_id=streamer.id)
        db.commit()
        return streamer, token

    def set_status(self, db: Session, streamer_id: int, status: str) -> Streamer:
        streamer = self.get(db, streamer_id)
        streamer.status = status
        if status == StreamerStatus.REVOKED:
            streamer.api_token_hash = hash_api_token(generate_api_token(), self.settings.token_hash_pepper)
        streamer.updated_at = utcnow()
        audit(db, action=f"streamer.{status}", result="success", streamer_id=streamer.id)
        db.commit()
        return streamer

    def accounts(self, db: Session, streamer_id: int) -> list[tuple[MinecraftAccount, KickAccount]]:
        self.get(db, streamer_id)
        rows = db.execute(
            select(MinecraftAccount, KickAccount)
            .join(KickAccount, KickAccount.minecraft_account_id == MinecraftAccount.id)
            .where(MinecraftAccount.streamer_id == streamer_id)
            .order_by(KickAccount.linked_at.desc())
        ).all()
        return [(row[0], row[1]) for row in rows]

    def stats(self, db: Session, streamer_id: int) -> dict:
        self.get(db, streamer_id)
        linked = db.scalar(
            select(func.count(KickAccount.id)).where(KickAccount.streamer_id == streamer_id)
        ) or 0
        sent = db.scalar(
            select(func.count(MessageEvent.id)).where(
                MessageEvent.streamer_id == streamer_id,
                MessageEvent.success.is_(True),
            )
        ) or 0
        failed = db.scalar(
            select(func.count(MessageEvent.id)).where(
                MessageEvent.streamer_id == streamer_id,
                MessageEvent.success.is_(False),
            )
        ) or 0
        since = utcnow() - timedelta(hours=24)
        last_day = db.scalar(
            select(func.count(MessageEvent.id)).where(
                MessageEvent.streamer_id == streamer_id,
                MessageEvent.success.is_(True),
                MessageEvent.created_at >= since,
            )
        ) or 0
        return {
            "linked_accounts": int(linked),
            "messages_sent": int(sent),
            "messages_failed": int(failed),
            "messages_last_24h": int(last_day),
        }


def _name(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned or len(cleaned) > 64 or not NAME_RE.fullmatch(cleaned):
        raise AppError("invalid_request", "Nombre de streamer inválido", 400)
    return cleaned
