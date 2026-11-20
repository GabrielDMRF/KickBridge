from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import AuditLog


def utcnow() -> datetime:
    # UTC sin tzinfo: SQLite devuelve datetimes naive y así las comparaciones son estables.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def audit(
    db: Session,
    *,
    action: str,
    result: str,
    streamer_id: int | None = None,
    minecraft_uuid: str | None = None,
    detail: str = "",
) -> None:
    safe_detail = " ".join(detail.split())[:300]
    db.add(
        AuditLog(
            streamer_id=streamer_id,
            minecraft_uuid=minecraft_uuid,
            action=action[:64],
            result=result[:32],
            detail=safe_detail,
            created_at=utcnow(),
        )
    )
