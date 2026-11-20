from __future__ import annotations

import base64
import hashlib
import secrets


def generate_code_verifier() -> str:
    # 64 bytes -> 86 caracteres URL-safe, dentro del rango 43..128 de RFC 7636.
    return secrets.token_urlsafe(64)


def code_challenge_s256(verifier: str) -> str:
    if not 43 <= len(verifier) <= 128:
        raise ValueError("El code_verifier PKCE debe tener entre 43 y 128 caracteres")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
