from __future__ import annotations

import html
import logging
from datetime import timedelta
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import OAUTH_SCOPES, Settings
from app.core.errors import AppError
from app.models import KickAccount, LinkSession, MinecraftAccount, Streamer
from app.security.crypto import TokenCipher
from app.security.hashing import new_link_code, new_state, sha256_hex
from app.security.pkce import code_challenge_s256, generate_code_verifier
from app.services.audit import audit, utcnow
from app.services.kick_client import KickClient, KickRequestError, TokenSet, scopes_allow_chat

log = logging.getLogger(__name__)


def render_page(title: str, paragraph: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="referrer" content="no-referrer">
  <title>{html.escape(title)}</title>
</head>
<body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#0e1116;color:#f4f7fb;font-family:Segoe UI,sans-serif">
  <main style="max-width:34rem;padding:2rem;text-align:center">
    <h1 style="margin-bottom:.5rem">{html.escape(title)}</h1>
    <p style="line-height:1.5;color:#c5d0dc">{paragraph}</p>
    <p style="color:#8ea0b5">Puedes cerrar esta ventana y volver a Minecraft.</p>
  </main>
</body>
</html>"""


class LinkingService:
    def __init__(self, settings: Settings, kick: KickClient, cipher: TokenCipher) -> None:
        self.settings = settings
        self.kick = kick
        self.cipher = cipher

    def start(
        self,
        db: Session,
        streamer: Streamer,
        minecraft_uuid: str,
        minecraft_username: str,
        expiration_seconds: int | None,
    ) -> tuple[str, int]:
        existing = self._active_kick(db, streamer.id, minecraft_uuid)
        if existing is not None:
            raise AppError("already_linked", "Este jugador ya tiene una cuenta de Kick vinculada", 409)
        ttl = self._ttl(expiration_seconds)
        since = utcnow() - timedelta(seconds=self.settings.link_start_rate_window_seconds)
        recent = db.scalar(
            select(func.count(LinkSession.id)).where(
                LinkSession.streamer_id == streamer.id,
                LinkSession.minecraft_uuid == minecraft_uuid,
                LinkSession.created_at >= since,
            )
        ) or 0
        if int(recent) >= self.settings.link_start_rate_limit:
            raise AppError("rate_limited", "Demasiados intentos de vinculación. Espera unos minutos.", 429)
        db.execute(
            delete(LinkSession).where(
                LinkSession.streamer_id == streamer.id,
                LinkSession.minecraft_uuid == minecraft_uuid,
                LinkSession.used_at.is_(None),
            )
        )
        code = new_link_code()
        state = new_state()
        verifier = generate_code_verifier()
        now = utcnow()
        session = LinkSession(
            streamer_id=streamer.id,
            minecraft_uuid=minecraft_uuid,
            minecraft_username=minecraft_username,
            code_hash=sha256_hex(code),
            state_enc=self.cipher.encrypt(state),
            state_hash=sha256_hex(state),
            verifier_enc=self.cipher.encrypt(verifier),
            code_challenge=code_challenge_s256(verifier),
            expires_at=now + timedelta(seconds=ttl),
            used_at=None,
            created_at=now,
        )
        db.add(session)
        audit(
            db,
            action="link.start",
            result="success",
            streamer_id=streamer.id,
            minecraft_uuid=minecraft_uuid,
        )
        db.commit()
        url = f"{self.settings.public_base_url}/v1/oauth/start/{code}"
        return url, ttl

    def authorization_redirect(self, db: Session, code: str) -> str:
        session = db.scalar(select(LinkSession).where(LinkSession.code_hash == sha256_hex(code)))
        if session is None or session.used_at is not None or session.expires_at <= utcnow():
            raise AppError("link_expired", "El enlace de vinculación no es válido o ya expiró", 410)
        try:
            state = self.cipher.decrypt(session.state_enc)
        except ValueError as exc:
            raise AppError("link_expired", "El enlace de vinculación no es válido o ya expiró", 410) from exc
        return self.kick.authorize_url(state=state, code_challenge=session.code_challenge)

    async def complete(self, db: Session, state: str | None, code: str | None, error: str | None) -> str:
        if error:
            audit(db, action="link.callback", result="failure", detail="oauth_denied")
            db.commit()
            return render_page("Autorización cancelada", "Kick no entregó la autorización. Vuelve a usar /kickchat link.")
        if not state or not code:
            return render_page("Vinculación incompleta", "La respuesta de Kick no incluía el código y el state esperados.")
        session = db.scalar(select(LinkSession).where(LinkSession.state_hash == sha256_hex(state)))
        if session is None or session.expires_at <= utcnow():
            audit(db, action="link.callback", result="failure", detail="state_invalid")
            db.commit()
            return render_page("Vinculación rechazada", "El state no coincide con una vinculación vigente.")
        claimed = db.execute(
            update(LinkSession)
            .where(LinkSession.id == session.id, LinkSession.used_at.is_(None))
            .values(used_at=utcnow())
        )
        if claimed.rowcount != 1:
            db.rollback()
            return render_page("Enlace ya usado", "Este código de vinculación ya fue utilizado.")
        db.commit()
        db.refresh(session)
        try:
            stored_state = self.cipher.decrypt(session.state_enc)
            verifier = self.cipher.decrypt(session.verifier_enc)
        except ValueError:
            self._drop_session(db, session.id)
            db.commit()
            return render_page("Vinculación rechazada", "No se pudo validar la sesión de vinculación.")
        if stored_state != state:
            self._drop_session(db, session.id)
            audit(db, action="link.callback", result="failure", streamer_id=session.streamer_id, minecraft_uuid=session.minecraft_uuid, detail="state_mismatch")
            db.commit()
            return render_page("Vinculación rechazada", "La validación de state falló.")
        try:
            tokens = await self.kick.exchange_authorization_code(code, verifier)
            if not tokens.scope or not scopes_allow_chat(tokens.scope):
                await self._revoke_pair(tokens)
                raise AppError("missing_scope", "Kick no concedió user:read y chat:write", 403)
            identity = await self.kick.get_current_user(tokens.access_token)
        except (KickRequestError, AppError) as exc:
            await self._revoke_unknown(code)
            self._drop_session(db, session.id)
            detail = exc.code if isinstance(exc, AppError) else f"kick_{exc.status}"
            audit(
                db,
                action="link.callback",
                result="failure",
                streamer_id=session.streamer_id,
                minecraft_uuid=session.minecraft_uuid,
                detail=detail,
            )
            db.commit()
            log.info("link failed streamer=%s uuid=%s detail=%s", session.streamer_id, session.minecraft_uuid, detail)
            return render_page("No se pudo vincular", "Kick no completó la autorización. Inténtalo de nuevo desde Minecraft.")
        conflict = db.scalar(
            select(KickAccount).where(
                KickAccount.streamer_id == session.streamer_id,
                KickAccount.kick_user_id == identity.user_id,
            )
        )
        if conflict is not None:
            await self._revoke_pair(tokens)
            self._drop_session(db, session.id)
            audit(db, action="link.callback", result="failure", streamer_id=session.streamer_id, minecraft_uuid=session.minecraft_uuid, detail="kick_already_linked")
            db.commit()
            return render_page(
                "Cuenta ya vinculada",
                "Esa cuenta de Kick ya está vinculada a otro jugador de este servidor.",
            )
        try:
            self._persist_link(db, session, identity.user_id, identity.username, tokens)
        except (IntegrityError, AppError):
            db.rollback()
            await self._revoke_pair(tokens)
            self._drop_session(db, session.id)
            db.commit()
            return render_page("No se pudo vincular", "La cuenta ya está asociada en este servidor.")
        self._drop_session(db, session.id)
        audit(
            db,
            action="link.complete",
            result="success",
            streamer_id=session.streamer_id,
            minecraft_uuid=session.minecraft_uuid,
            detail=f"kick_user={identity.user_id}",
        )
        db.commit()
        safe_name = html.escape(identity.username)
        return render_page("Cuenta vinculada", f"Tu cuenta de Kick <strong>{safe_name}</strong> quedó vinculada. Vuelve a Minecraft.")

    def _persist_link(self, db: Session, session: LinkSession, kick_user_id: int, kick_username: str, tokens: TokenSet) -> None:
        now = utcnow()
        account = db.scalar(
            select(MinecraftAccount).where(
                MinecraftAccount.streamer_id == session.streamer_id,
                MinecraftAccount.uuid == session.minecraft_uuid,
            )
        )
        if account is None:
            account = MinecraftAccount(
                streamer_id=session.streamer_id,
                uuid=session.minecraft_uuid,
                username=session.minecraft_username,
                created_at=now,
                updated_at=now,
            )
            db.add(account)
            db.flush()
        else:
            account.username = session.minecraft_username
            account.updated_at = now
        if account.kick_account is not None:
            raise AppError("already_linked", "Este jugador ya tiene una cuenta de Kick vinculada", 409)
        scope = tokens.scope or OAUTH_SCOPES
        if not tokens.refresh_token:
            raise AppError("oauth_failed", "Kick no entregó refresh token", 502)
        kick = KickAccount(
            streamer_id=session.streamer_id,
            minecraft_account_id=account.id,
            kick_user_id=kick_user_id,
            kick_username=kick_username,
            access_token_enc=self.cipher.encrypt(tokens.access_token),
            refresh_token_enc=self.cipher.encrypt(tokens.refresh_token),
            access_expires_at=now + timedelta(seconds=tokens.expires_in),
            refresh_expires_at=(now + timedelta(seconds=tokens.refresh_expires_in)) if tokens.refresh_expires_in else None,
            scopes=scope[:256],
            status="active",
            linked_at=now,
            updated_at=now,
        )
        db.add(kick)
        db.flush()

    async def unlink(self, db: Session, streamer: Streamer, minecraft_uuid: str) -> None:
        account = self._active_kick(db, streamer.id, minecraft_uuid)
        if account is None:
            raise AppError("not_linked", "Este jugador no tiene una cuenta de Kick vinculada", 404)
        access = self._decrypt_or_blank(account.access_token_enc)
        refresh = self._decrypt_or_blank(account.refresh_token_enc)
        minecraft = account.minecraft_account
        db.delete(account)
        audit(db, action="link.unlink", result="success", streamer_id=streamer.id, minecraft_uuid=minecraft_uuid)
        db.commit()
        if refresh:
            await self.kick.revoke(refresh, "refresh_token")
        elif access:
            await self.kick.revoke(access, "access_token")
        log.info("unlinked streamer=%s uuid=%s kick_user=%s", streamer.id, minecraft_uuid, account.kick_user_id)
        _ = minecraft

    def status(self, db: Session, streamer: Streamer, minecraft_uuid: str) -> dict:
        account = db.scalar(
            select(MinecraftAccount).where(
                MinecraftAccount.streamer_id == streamer.id,
                MinecraftAccount.uuid == minecraft_uuid,
            )
        )
        if account is None or account.kick_account is None or account.kick_account.status != "active":
            return {"linked": False, "minecraft_uuid": minecraft_uuid}
        kick = account.kick_account
        return {
            "linked": True,
            "minecraft_uuid": account.uuid,
            "minecraft_username": account.username,
            "kick_user_id": kick.kick_user_id,
            "kick_username": kick.kick_username,
            "linked_at": kick.linked_at.isoformat(),
        }

    def _active_kick(self, db: Session, streamer_id: int, minecraft_uuid: str) -> KickAccount | None:
        account = db.scalar(
            select(MinecraftAccount).where(
                MinecraftAccount.streamer_id == streamer_id,
                MinecraftAccount.uuid == minecraft_uuid,
            )
        )
        if account is None or account.kick_account is None or account.kick_account.status != "active":
            return None
        return account.kick_account

    def _ttl(self, requested: int | None) -> int:
        ttl = self.settings.link_ttl_seconds if requested is None else requested
        if ttl < self.settings.link_ttl_min_seconds or ttl > self.settings.link_ttl_max_seconds:
            raise AppError("invalid_request", "La caducidad de la vinculación está fuera del rango permitido", 400)
        return ttl

    def _drop_session(self, db: Session, session_id: int) -> None:
        db.execute(delete(LinkSession).where(LinkSession.id == session_id))

    def _decrypt_or_blank(self, value: str) -> str:
        try:
            return self.cipher.decrypt(value)
        except ValueError:
            return ""

    async def _revoke_pair(self, tokens: TokenSet) -> None:
        if tokens.refresh_token:
            await self.kick.revoke(tokens.refresh_token, "refresh_token")
        await self.kick.revoke(tokens.access_token, "access_token")

    async def _revoke_unknown(self, _authorization_code: str) -> None:
        return
