from __future__ import annotations

import os
from base64 import b64decode, b64encode

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_SIZE = 12


class TokenCipher:
    """AES-256-GCM. El resultado es Base64(nonce || ciphertext || tag)."""

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("La clave AES-256-GCM debe tener 32 bytes")
        self._aes = AESGCM(key)

    def encrypt(self, plaintext: str) -> str:
        if plaintext is None or plaintext == "":
            raise ValueError("No se cifra un secreto vacío")
        nonce = os.urandom(NONCE_SIZE)
        ciphertext = self._aes.encrypt(nonce, plaintext.encode("utf-8"), None)
        return b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, encoded: str) -> str:
        try:
            raw = b64decode(encoded, validate=True)
            if len(raw) <= NONCE_SIZE:
                raise ValueError("ciphertext corto")
            nonce, ciphertext = raw[:NONCE_SIZE], raw[NONCE_SIZE:]
            return self._aes.decrypt(nonce, ciphertext, None).decode("utf-8")
        except Exception as exc:
            raise ValueError("No se pudo descifrar el secreto") from exc
