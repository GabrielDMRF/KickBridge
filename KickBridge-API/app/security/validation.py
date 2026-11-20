from __future__ import annotations

import re
import unicodedata

import regex

from app.core.errors import AppError

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
USERNAME_RE = re.compile(r"[A-Za-z0-9_]{1,16}")
LINK_CODE_RE = re.compile(r"[A-Za-z0-9_-]{16,80}")
NONCE_RE = re.compile(r"[A-Za-z0-9_-]{16,80}")
SLUG_RE = re.compile(r"[A-Za-z0-9_-]{1,25}")

BIDI_CONTROLS = {0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069}
KICK_MAX_GRAPHEMES = 500
KICK_MAX_UTF8_BYTES = 2048


def normalize_uuid(value: str) -> str:
    raw = (value or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{32}", raw):
        raw = f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"
    if not UUID_RE.fullmatch(raw):
        raise AppError("invalid_request", "UUID de Minecraft inválido", 400)
    return raw


def validate_username(value: str) -> str:
    name = (value or "").strip()
    if not USERNAME_RE.fullmatch(name):
        raise AppError("invalid_request", "Nombre de Minecraft inválido", 400)
    return name


def validate_link_code(value: str) -> str:
    code = (value or "").strip()
    if not LINK_CODE_RE.fullmatch(code):
        raise AppError("invalid_request", "Código de vinculación inválido", 400)
    return code


def validate_nonce(value: str) -> str:
    nonce = (value or "").strip()
    if not NONCE_RE.fullmatch(nonce):
        raise AppError("invalid_request", "Cabeceras de seguridad inválidas", 401)
    return nonce


def validate_slug(value: str) -> str:
    slug = (value or "").strip()
    if not SLUG_RE.fullmatch(slug):
        raise AppError("invalid_request", "Slug de canal inválido", 400)
    return slug


def grapheme_length(value: str) -> int:
    return len(regex.findall(r"\X", value))


def validate_chat_content(content: str) -> str:
    if not isinstance(content, str):
        raise AppError("invalid_message", "El mensaje no es válido", 400)
    cleaned = content.strip()
    if not cleaned:
        raise AppError("invalid_message", "El mensaje está vacío", 400)
    for char in cleaned:
        category = unicodedata.category(char)
        if category in {"Cc", "Cs", "Co"} or ord(char) in BIDI_CONTROLS:
            raise AppError("invalid_message", "El mensaje contiene caracteres no permitidos", 400)
    if grapheme_length(cleaned) > KICK_MAX_GRAPHEMES:
        raise AppError("message_too_long", "El mensaje supera 500 caracteres", 400)
    if len(cleaned.encode("utf-8")) > KICK_MAX_UTF8_BYTES:
        raise AppError("message_too_long", "El mensaje supera el tamaño permitido por Kick", 400)
    return cleaned
