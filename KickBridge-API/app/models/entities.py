from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class StreamerStatus:
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class Streamer(Base):
    __tablename__ = "streamers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    kick_broadcaster_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    api_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=StreamerStatus.ACTIVE, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    minecraft_accounts: Mapped[list[MinecraftAccount]] = relationship(
        back_populates="streamer",
        cascade="all, delete-orphan",
    )


class MinecraftAccount(Base):
    __tablename__ = "minecraft_accounts"
    __table_args__ = (UniqueConstraint("streamer_id", "uuid", name="uq_mc_streamer_uuid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    streamer_id: Mapped[int] = mapped_column(ForeignKey("streamers.id", ondelete="CASCADE"), nullable=False, index=True)
    uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    username: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    streamer: Mapped[Streamer] = relationship(back_populates="minecraft_accounts")
    kick_account: Mapped[KickAccount | None] = relationship(
        back_populates="minecraft_account",
        cascade="all, delete-orphan",
        uselist=False,
    )


class KickAccount(Base):
    __tablename__ = "kick_accounts"
    __table_args__ = (UniqueConstraint("streamer_id", "kick_user_id", name="uq_kick_streamer_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    streamer_id: Mapped[int] = mapped_column(ForeignKey("streamers.id", ondelete="CASCADE"), nullable=False, index=True)
    minecraft_account_id: Mapped[int] = mapped_column(
        ForeignKey("minecraft_accounts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    kick_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kick_username: Mapped[str] = mapped_column(String(64), nullable=False)
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    minecraft_account: Mapped[MinecraftAccount] = relationship(back_populates="kick_account")


class LinkSession(Base):
    __tablename__ = "link_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    streamer_id: Mapped[int] = mapped_column(ForeignKey("streamers.id", ondelete="CASCADE"), nullable=False, index=True)
    minecraft_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    minecraft_username: Mapped[str] = mapped_column(String(16), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    state_enc: Mapped[str] = mapped_column(Text, nullable=False)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    verifier_enc: Mapped[str] = mapped_column(Text, nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_streamer_created", "streamer_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    streamer_id: Mapped[int | None] = mapped_column(ForeignKey("streamers.id", ondelete="SET NULL"), nullable=True)
    minecraft_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class MessageEvent(Base):
    __tablename__ = "message_events"
    __table_args__ = (Index("ix_message_streamer_player_created", "streamer_id", "minecraft_uuid", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    streamer_id: Mapped[int] = mapped_column(ForeignKey("streamers.id", ondelete="CASCADE"), nullable=False)
    minecraft_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    kick_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    kick_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kick_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class RequestNonce(Base):
    __tablename__ = "request_nonces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    streamer_id: Mapped[int] = mapped_column(ForeignKey("streamers.id", ondelete="CASCADE"), nullable=False, index=True)
    nonce_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
