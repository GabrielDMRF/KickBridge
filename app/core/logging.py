from __future__ import annotations

import logging
import re

SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)\S+"),
    re.compile(r"(?i)(access_token|refresh_token|client_secret|code_verifier|api_token|token_encryption_key)(\s*[=:]\s*)\S+"),
    re.compile(r"(?i)(kb_[A-Za-z0-9_\-]{8,})"),
)


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = tuple(redact(arg) if isinstance(arg, str) else arg for arg in record.args)
        return True


def redact(value: str) -> str:
    cleaned = value
    for pattern in SECRET_PATTERNS:
        cleaned = pattern.sub(lambda match: _mask(match), cleaned)
    return cleaned


def _mask(match: re.Match[str]) -> str:
    groups = [group for group in match.groups() if group]
    if not groups:
        return "[redacted]"
    if len(groups) >= 2 and groups[0].lower() in {
        "access_token",
        "refresh_token",
        "client_secret",
        "code_verifier",
        "api_token",
        "token_encryption_key",
    }:
        return f"{groups[0]}{groups[1]}[redacted]"
    if groups[0].lower().startswith("bearer"):
        return "Bearer [redacted]"
    return "[redacted]"


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    redact_filter = RedactFilter()
    logging.getLogger().addFilter(redact_filter)
    for handler in logging.getLogger().handlers:
        handler.addFilter(redact_filter)
