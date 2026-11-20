from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.logging import redact
from app.database.base import Base
from app.security.crypto import TokenCipher
from app.security.hashing import generate_api_token, hash_api_token, secrets_equal
from app.security.pkce import code_challenge_s256
from tests.conftest import admin_headers, create_streamer, link_player, plugin_headers


def test_aes_gcm_roundtrip_and_tamper() -> None:
    cipher = TokenCipher(b"0123456789abcdef0123456789abcdef")
    encoded = cipher.encrypt("refresh-token-value")
    assert cipher.decrypt(encoded) == "refresh-token-value"
    raw = bytearray(base64.b64decode(encoded))
    raw[-1] ^= 0x01
    with pytest.raises(ValueError):
        cipher.decrypt(base64.b64encode(bytes(raw)).decode())


def test_pkce_s256_rfc7636_vector() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert code_challenge_s256(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_api_token_is_peppered_hash() -> None:
    token = generate_api_token()
    digest = hash_api_token(token, "pepper-for-tests-ok")
    assert digest != token
    assert token not in digest
    assert secrets_equal("admin-token-for-tests-32-characters", "admin-token-for-tests-32-characters")
    assert not secrets_equal("admin-token-for-tests-32-characters", "admin-token-for-tests-32-characters!")


def test_logs_redact_bearer_and_tokens() -> None:
    cleaned = redact("Authorization Bearer kb_supersecretvalue access_token=abcdef refresh_token=zzzz")
    assert "kb_supersecretvalue" not in cleaned
    assert "abcdef" not in cleaned
    assert "Bearer [redacted]" in cleaned


def test_https_is_required_except_health() -> None:
    from app.core.factory import create_app

    key = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
    settings = Settings(
        _env_file=None,
        kick_client_id="client-id",
        kick_client_secret="client-secret-value",
        public_base_url="https://bridge.example.com",
        token_encryption_key=key,
        token_hash_pepper="pepper-for-tests-ok",
        admin_api_token="admin-token-for-tests-32-characters",
        database_url="sqlite://",
        require_https=True,
        trust_proxy=False,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        denied = client.get("/v1/admin/streamers", headers=admin_headers())
        assert denied.status_code == 400
        assert denied.json()["error"]["code"] == "https_required"


def test_rejects_replay_bad_timestamp_and_sql_in_username(client: TestClient) -> None:
    token = create_streamer(client)
    nonce = "nonce-replay-fixed-0001"
    headers = plugin_headers(token, nonce=nonce)
    payload = {"minecraft_username": "Steve", "expiration_seconds": 300}
    player = "22222222-2222-4222-8222-222222222222"
    first = client.post(f"/v1/players/{player}/link", headers=headers, json=payload)
    assert first.status_code == 200, first.text
    second = client.post(f"/v1/players/{player}/link", headers=headers, json=payload)
    assert second.status_code == 401
    assert second.json()["error"]["code"] == "replay_rejected"
    stale = client.post(
        f"/v1/players/{player}/link",
        headers=plugin_headers(token, timestamp=1),
        json=payload,
    )
    assert stale.status_code == 401
    injected = client.post(
        f"/v1/players/{player}/link",
        headers=plugin_headers(token),
        json={"minecraft_username": "aa';drop", "expiration_seconds": 300},
    )
    assert injected.status_code == 400
    listed = client.get("/v1/admin/streamers", headers=admin_headers())
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_wrong_streamer_token_and_suspended(client: TestClient) -> None:
    token = create_streamer(client)
    denied = client.get(
        "/v1/players/33333333-3333-4333-8333-333333333333",
        headers=plugin_headers("kb_not-a-real-token"),
    )
    assert denied.status_code == 401
    created = client.post(
        "/v1/admin/streamers",
        headers=admin_headers(),
        json={"name": "Otro", "kick_broadcaster_user_id": 12},
    )
    streamer_id = created.json()["id"]
    assert client.post(f"/v1/admin/streamers/{streamer_id}/suspend", headers=admin_headers()).status_code == 200
    other_token = created.json()["api_token"]
    suspended = client.get(
        "/v1/players/33333333-3333-4333-8333-333333333333",
        headers=plugin_headers(other_token),
    )
    assert suspended.status_code == 403
    assert suspended.json()["error"]["code"] == "streamer_suspended"
    assert token.startswith("kb_")


def test_chat_content_is_not_stored_and_error_hides_secrets(client: TestClient) -> None:
    token = create_streamer(client)
    link_player(client, token)
    sent = client.post(
        "/v1/players/11111111-1111-4111-8111-111111111111/chat",
        headers=plugin_headers(token),
        json={"content": "' OR 1=1 --"},
    )
    assert sent.status_code == 200, sent.text
    client.app.state.kick.fail_chat_status = 500
    failed = client.post(
        "/v1/players/11111111-1111-4111-8111-111111111111/chat",
        headers=plugin_headers(token),
        json={"content": "hola"},
    )
    assert failed.status_code == 502
    assert "client-secret-value" not in failed.text
    assert "access-player-token" not in failed.text
    assert "refresh-player-token" not in failed.text
    audit = client.get("/v1/admin/audit", headers=admin_headers()).text
    assert "access-player-token" not in audit
    assert "' OR 1=1 --" not in audit
