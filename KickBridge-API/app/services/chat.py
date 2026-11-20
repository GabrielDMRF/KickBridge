from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models import KickAccount, MessageEvent, MinecraftAccount, Streamer
from app.security.crypto import TokenCipher
from app.services.audit import audit, utcnow
from app.services.kick_client import KickClient, KickRequestError, TokenSet, scopes_allow_chat

log = logging.getLogger(__name__)

_locks: dict[int, asyncio.Lock] = {}


def _lock(account_id: int) -> asyncio.Lock:
    lock = _locks.get(account_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[account_id] = lock
    return lock


class ChatService:
    def __init__(self, settings: Settings, kick: KickClient, cipher: TokenCipher) -> None:
        self.settings = settings
        self.kick = kick
        self.cipher = cipher

    async def send(self, db: Session, streamer: Streamer, minecraft_uuid: str, content: str) -> dict:
        account = db.scalar(
            select(MinecraftAccount).where(
                MinecraftAccount.streamer_id == streamer.id,
                MinecraftAccount.uuid == minecraft_uuid,
            )
        )
        kick_account = account.kick_account if account is not None else None
        if account is None or kick_account is None or kick_account.status != "active":
            raise AppError("not_linked", "Debes vincular tu cuenta de Kick antes de enviar mensajes", 403)
        self._enforce_limits(db, streamer.id, minecraft_uuid)
        access = await self._valid_access_token(db, kick_account)
        event = MessageEvent(
            streamer_id=streamer.id,
            minecraft_uuid=minecraft_uuid,
            kick_user_id=kick_account.kick_user_id,
            success=False,
            kick_status=None,
            kick_message_id=None,
            created_at=utcnow(),
        )
        db.add(event)
        db.commit()
        try:
            result = await self.kick.post_user_chat(access, streamer.kick_broadcaster_user_id, content)
        except KickRequestError as exc:
            if exc.status == 401:
                access = await self._force_refresh(db, kick_account)
                try:
                    result = await self.kick.post_user_chat(access, streamer.kick_broadcaster_user_id, content)
                except KickRequestError as retry_exc:
                    self._mark(db, event, False, retry_exc.status, None, streamer.id, minecraft_uuid, "kick_rejected")
                    raise _from_kick(retry_exc) from retry_exc
            else:
                self._mark(db, event, False, exc.status, None, streamer.id, minecraft_uuid, "kick_rejected")
                raise _from_kick(exc) from exc
        if not result.is_sent:
            self._mark(db, event, False, 200, result.message_id, streamer.id, minecraft_uuid, "not_sent")
            raise AppError("not_sent", "Kick no confirmó el envío del mensaje", 502, kick_status=200)
        self._mark(db, event, True, 200, result.message_id, streamer.id, minecraft_uuid, "sent")
        log.info(
            "chat sent streamer=%s uuid=%s kick_user=%s",
            streamer.id,
            minecraft_uuid,
            kick_account.kick_user_id,
        )
        return {"sent": True, "message_id": result.message_id}

    def _enforce_limits(self, db: Session, streamer_id: int, minecraft_uuid: str) -> None:
        now = utcnow()
        last = db.scalar(
            select(MessageEvent.created_at)
            .where(
                MessageEvent.streamer_id == streamer_id,
                MessageEvent.minecraft_uuid == minecraft_uuid,
            )
            .order_by(MessageEvent.created_at.desc())
            .limit(1)
        )
        if last is not None and self.settings.chat_cooldown_seconds > 0:
            elapsed = (now - last).total_seconds()
            if elapsed < self.settings.chat_cooldown_seconds:
                retry_after = max(1, int(self.settings.chat_cooldown_seconds - elapsed + 0.999))
                raise AppError(
                    "cooldown",
                    "Espera antes de enviar otro mensaje",
                    429,
                    retry_after=retry_after,
                )
        window_start = now - timedelta(seconds=self.settings.chat_rate_window_seconds)
        recent = db.scalar(
            select(func.count(MessageEvent.id)).where(
                MessageEvent.streamer_id == streamer_id,
                MessageEvent.minecraft_uuid == minecraft_uuid,
                MessageEvent.created_at >= window_start,
            )
        ) or 0
        if int(recent) >= self.settings.chat_rate_limit:
            raise AppError("rate_limited", "Has enviado demasiados mensajes. Espera un momento.", 429, retry_after=self.settings.chat_rate_window_seconds)

    async def _valid_access_token(self, db: Session, account: KickAccount) -> str:
        skew = timedelta(seconds=self.settings.access_refresh_skew_seconds)
        if account.access_expires_at - skew > utcnow():
            return self.cipher.decrypt(account.access_token_enc)
        return await self._force_refresh(db, account)

    async def _force_refresh(self, db: Session, account: KickAccount) -> str:
        async with _lock(account.id):
            db.refresh(account)
            skew = timedelta(seconds=self.settings.access_refresh_skew_seconds)
            if account.access_expires_at - skew > utcnow():
                return self.cipher.decrypt(account.access_token_enc)
            try:
                refresh_token = self.cipher.decrypt(account.refresh_token_enc)
                tokens = await self.kick.refresh(refresh_token)
            except (KickRequestError, ValueError) as exc:
                self._drop_account(db, account, "refresh_failed")
                raise AppError("reauth_required", "Tu sesión de Kick expiró. Vuelve a vincular la cuenta.", 401) from exc
            if tokens.scope and not scopes_allow_chat(tokens.scope):
                await self.kick.revoke(tokens.access_token, "access_token")
                if tokens.refresh_token:
                    await self.kick.revoke(tokens.refresh_token, "refresh_token")
                self._drop_account(db, account, "scope_revoked")
                raise AppError("reauth_required", "Kick retiró el permiso para enviar mensajes. Vuelve a vincular la cuenta.", 401)
            self._apply_tokens(account, tokens)
            db.commit()
            return tokens.access_token

    def _apply_tokens(self, account: KickAccount, tokens: TokenSet) -> None:
        now = utcnow()
        account.access_token_enc = self.cipher.encrypt(tokens.access_token)
        if tokens.refresh_token:
            account.refresh_token_enc = self.cipher.encrypt(tokens.refresh_token)
        account.access_expires_at = now + timedelta(seconds=tokens.expires_in)
        if tokens.refresh_expires_in:
            account.refresh_expires_at = now + timedelta(seconds=tokens.refresh_expires_in)
        if tokens.scope:
            account.scopes = tokens.scope[:256]
        account.updated_at = now

    def _drop_account(self, db: Session, account: KickAccount, detail: str) -> None:
        minecraft = db.get(MinecraftAccount, account.minecraft_account_id)
        uuid = minecraft.uuid if minecraft is not None else None
        streamer_id = account.streamer_id
        db.delete(account)
        audit(db, action="link.invalidate", result="failure", streamer_id=streamer_id, minecraft_uuid=uuid, detail=detail)
        db.commit()

    def _mark(
        self,
        db: Session,
        event: MessageEvent,
        success: bool,
        kick_status: int | None,
        message_id: str | None,
        streamer_id: int,
        minecraft_uuid: str,
        detail: str,
    ) -> None:
        event.success = success
        event.kick_status = kick_status
        event.kick_message_id = message_id[:36] if message_id else None
        audit(
            db,
            action="chat.send",
            result="success" if success else "failure",
            streamer_id=streamer_id,
            minecraft_uuid=minecraft_uuid,
            detail=detail,
        )
        db.commit()


def _from_kick(exc: KickRequestError) -> AppError:
    if exc.status == 400:
        return AppError("kick_rejected", "Kick rechazó el contenido del mensaje", 400, kick_status=400)
    if exc.status == 401:
        return AppError("reauth_required", "Tu sesión de Kick expiró. Vuelve a vincular la cuenta.", 401, kick_status=401)
    if exc.status == 403:
        return AppError(
            "kick_forbidden",
            "Kick denegó el mensaje en ese canal. Pueden aplicarse las reglas del chat o una restricción del broadcaster. No se reintenta con otra identidad.",
            403,
            kick_status=403,
        )
    if exc.status == 404:
        return AppError("kick_not_found", "Kick no encontró el canal configurado", 404, kick_status=404)
    if exc.status == 429:
        return AppError("kick_rate_limited", "Kick limitó el envío. Espera un momento.", 429, kick_status=429, retry_after=10)
    return AppError("kick_unavailable", "Kick no pudo aceptar el mensaje", 502, kick_status=exc.status)
