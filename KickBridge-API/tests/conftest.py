from __future__ import annotations

import base64
import time
import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.database.base import Base
from app.services.kick_client import ChatSendResult, KickIdentity, KickRequestError, TokenSet


class FakeKick:
    def __init__(self) -> None:
        self.chat_calls: list[dict] = []
        self.revoked: list[tuple[str, str]] = []
        self.exchanges = 0
        self.refresh_calls = 0
        self.fail_chat_status: int | None = None
        self.user_id = 4242
        self.username = "KickPlayer"
        self.scope = "user:read chat:write"
        self.access_token = "access-player-token"
        self.refresh_token = "refresh-player-token"

    def authorize_url(self, *, state: str, code_challenge: str) -> str:
        from urllib.parse import urlencode

        query = urlencode(
            {
                "response_type": "code",
                "client_id": "client-id",
                "redirect_uri": "https://bridge.example.com/v1/oauth/callback",
                "scope": "user:read chat:write",
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "state": state,
            }
        )
        return f"https://id.kick.com/oauth/authorize?{query}"

    async def exchange_authorization_code(self, code: str, code_verifier: str) -> TokenSet:
        assert code
        assert 43 <= len(code_verifier) <= 128
        self.exchanges += 1
        return TokenSet(self.access_token, self.refresh_token, 7200, 2592000, self.scope)

    async def refresh(self, refresh_token: str) -> TokenSet:
        assert refresh_token
        self.refresh_calls += 1
        return TokenSet("access-refreshed-token", "refresh-rotated-token", 7200, 2592000, self.scope)

    async def revoke(self, token: str, hint: str) -> None:
        self.revoked.append((hint, token))

    async def get_current_user(self, access_token: str) -> KickIdentity:
        assert access_token == self.access_token
        return KickIdentity(self.user_id, self.username)

    async def post_user_chat(self, access_token: str, broadcaster_user_id: int, content: str) -> ChatSendResult:
        self.chat_calls.append(
            {"access_token": access_token, "broadcaster_user_id": broadcaster_user_id, "content": content, "type": "user"}
        )
        if self.fail_chat_status:
            raise KickRequestError(self.fail_chat_status)
        if content == "NOPE":
            return ChatSendResult(message_id=None, is_sent=False)
        return ChatSendResult(message_id="828f83bb-e391-4c78-9e91-af35a172840e", is_sent=True)

    async def resolve_channel_slug(self, slug: str) -> tuple[int, str]:
        assert slug == "demo"
        return 555, "demo"

    async def aclose(self) -> None:
        return None


@pytest.fixture()
def settings() -> Settings:
    key = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
    return Settings(
        _env_file=None,
        kick_client_id="client-id",
        kick_client_secret="client-secret-value",
        public_base_url="https://bridge.example.com",
        token_encryption_key=key,
        token_hash_pepper="pepper-for-tests-ok",
        admin_api_token="admin-token-for-tests-32-characters",
        database_url="sqlite://",
        require_https=False,
        trust_proxy=False,
        link_ttl_seconds=300,
        chat_cooldown_seconds=0,
        chat_rate_limit=10,
        chat_rate_window_seconds=60,
        replay_window_seconds=120,
    )


@pytest.fixture()
def fake() -> FakeKick:
    return FakeKick()


@pytest.fixture()
def client(settings: Settings, fake: FakeKick):
    from app.core.factory import create_app

    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    app.state.kick = fake
    with TestClient(app) as test_client:
        yield test_client


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": "admin-token-for-tests-32-characters"}


def plugin_headers(token: str, nonce: str | None = None, timestamp: int | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-KB-Timestamp": str(timestamp if timestamp is not None else int(time.time())),
        "X-KB-Nonce": nonce or str(uuid.uuid4()),
    }


def create_streamer(client: TestClient, name: str = "Demo", broadcaster: int = 9001) -> str:
    response = client.post(
        "/v1/admin/streamers",
        headers=admin_headers(),
        json={"name": name, "kick_broadcaster_user_id": broadcaster},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["api_token"].startswith("kb_")
    assert "api_token_hash" not in body
    return body["api_token"]


def link_player(client: TestClient, token: str, player: str = "11111111-1111-4111-8111-111111111111", name: str = "Steve") -> None:
    started = client.post(
        f"/v1/players/{player}/link",
        headers=plugin_headers(token),
        json={"minecraft_username": name, "expiration_seconds": 300},
    )
    assert started.status_code == 200, started.text
    url = started.json()["url"]
    assert url.startswith("https://bridge.example.com/v1/oauth/start/")
    code = url.rstrip("/").split("/")[-1]
    redirect = client.get(f"/v1/oauth/start/{code}", follow_redirects=False)
    assert redirect.status_code == 302, redirect.text
    location = redirect.headers["location"]
    parsed = urlparse(location)
    assert parsed.netloc == "id.kick.com"
    query = parse_qs(parsed.query)
    assert query["code_challenge_method"] == ["S256"]
    assert "user:read" in query["scope"][0] and "chat:write" in query["scope"][0]
    assert "client_secret" not in location
    state = query["state"][0]
    callback = client.get("/v1/oauth/callback", params={"code": "kick-auth-code", "state": state})
    assert callback.status_code == 200, callback.text
    assert "KickPlayer" in callback.text
    assert "access-player-token" not in callback.text
    assert "client-secret-value" not in callback.text
