from __future__ import annotations

import base64
import logging
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)

OAUTH_SCOPES = "user:read chat:write"
USER_CHAT_TYPE = "user"


class Settings(BaseSettings):
    """Configuración cargada solo desde el entorno o un archivo .env local."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    kick_client_id: str = Field(min_length=1)
    kick_client_secret: str = Field(min_length=1)
    public_base_url: str
    token_encryption_key: str
    token_hash_pepper: str = Field(min_length=16)
    admin_api_token: str = Field(min_length=32)
    database_url: str = "sqlite:///./data/kickbridge.db"
    require_https: bool = True
    trust_proxy: bool = True
    link_ttl_seconds: int = 300
    link_ttl_max_seconds: int = 900
    link_ttl_min_seconds: int = 60
    chat_cooldown_seconds: int = 10
    chat_rate_limit: int = 5
    chat_rate_window_seconds: int = 30
    replay_window_seconds: int = 120
    access_refresh_skew_seconds: int = 60
    log_level: str = "INFO"
    kick_api_base: str = "https://api.kick.com"
    kick_oauth_base: str = "https://id.kick.com"
    link_start_rate_limit: int = 5
    link_start_rate_window_seconds: int = 600
    oauth_ip_rate_limit: int = 60
    oauth_ip_rate_window_seconds: int = 60

    @field_validator("public_base_url", "kick_api_base", "kick_oauth_base")
    @classmethod
    def _strip_url(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @field_validator("kick_client_id", "kick_client_secret", "admin_api_token", "token_hash_pepper")
    @classmethod
    def _strip_secret(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("valor vacío")
        return cleaned

    @property
    def kick_redirect_uri(self) -> str:
        return f"{self.public_base_url}/v1/oauth/callback"

    @property
    def encryption_key_bytes(self) -> bytes:
        try:
            raw = base64.b64decode(self.token_encryption_key.strip(), validate=True)
        except Exception as exc:
            raise ValueError("TOKEN_ENCRYPTION_KEY no es Base64 válido") from exc
        if len(raw) != 32:
            raise ValueError("TOKEN_ENCRYPTION_KEY debe decodificar a 32 bytes")
        return raw

    def validate_runtime(self) -> None:
        _ = self.encryption_key_bytes
        parsed = urlparse(self.public_base_url)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError("PUBLIC_BASE_URL no es una URL absoluta")
        if self.require_https and parsed.scheme != "https":
            raise ValueError("PUBLIC_BASE_URL debe usar HTTPS cuando REQUIRE_HTTPS=true")
        oauth = urlparse(self.kick_oauth_base)
        api = urlparse(self.kick_api_base)
        if oauth.scheme != "https" or api.scheme != "https":
            raise ValueError("Los hosts de Kick deben ser HTTPS")
        if self.link_ttl_min_seconds > self.link_ttl_max_seconds:
            raise ValueError("El TTL mínimo de vinculación supera al máximo")
        if self.chat_cooldown_seconds < 0:
            raise ValueError("CHAT_COOLDOWN_SECONDS no puede ser negativo")
        if self.chat_rate_limit < 1:
            raise ValueError("CHAT_RATE_LIMIT debe ser al menos 1")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
