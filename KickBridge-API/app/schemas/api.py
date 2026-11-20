from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LinkStartIn(BaseModel):
    minecraft_username: str = Field(min_length=1, max_length=16)
    expiration_seconds: int | None = Field(default=None, ge=60, le=900)


class ChatIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class StreamerCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    kick_broadcaster_user_id: int = Field(gt=0)


class StreamerUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    kick_broadcaster_user_id: int | None = Field(default=None, gt=0)


class SlugIn(BaseModel):
    slug: str = Field(min_length=1, max_length=25)


class StreamerOut(BaseModel):
    id: int
    name: str
    kick_broadcaster_user_id: int
    status: str
    created_at: datetime
    linked_accounts: int = 0
    api_token: str | None = None


class AccountOut(BaseModel):
    minecraft_uuid: str
    minecraft_username: str
    kick_user_id: int
    kick_username: str
    status: str
    linked_at: datetime


class StatsOut(BaseModel):
    linked_accounts: int
    messages_sent: int
    messages_failed: int
    messages_last_24h: int
