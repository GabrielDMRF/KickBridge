from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_api_token() -> str:
    return "kb_" + secrets.token_urlsafe(32)


def hash_api_token(token: str, pepper: str) -> str:
    return hmac.new(pepper.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def secrets_equal(left: str, right: str) -> bool:
    left_digest = hashlib.sha256(left.encode("utf-8")).digest()
    right_digest = hashlib.sha256(right.encode("utf-8")).digest()
    return hmac.compare_digest(left_digest, right_digest)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_state() -> str:
    return secrets.token_urlsafe(32)


def new_link_code() -> str:
    return secrets.token_urlsafe(18)
