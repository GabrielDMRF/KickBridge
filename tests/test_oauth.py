from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.services.kick_client import KickClient, build_user_chat_body
from tests.conftest import admin_headers, create_streamer, link_player, plugin_headers


def test_chat_body_is_user_not_shared_bot() -> None:
    body = build_user_chat_body(99, "hola")
    assert body == {"type": "user", "broadcaster_user_id": 99, "content": "hola"}
    assert "bot" not in body.values()


@pytest.mark.asyncio
async def test_kick_client_uses_documented_endpoints(settings) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/oauth/token":
            form = request.content.decode()
            assert "grant_type=authorization_code" in form
            assert "code_verifier=" in form
            assert "client_secret=" in form
            return httpx.Response(
                200,
                json={
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "expires_in": 7200,
                    "refresh_expires_in": 2592000,
                    "scope": "user:read chat:write",
                    "token_type": "Bearer",
                },
            )
        if request.url.path == "/public/v1/users":
            assert request.headers["Authorization"] == "Bearer access-1"
            return httpx.Response(
                200,
                json={
                    "message": "OK",
                    "data": [
                        {
                            "user_id": 77,
                            "name": "RealUser",
                            "email": "hidden@example.com",
                            "profile_picture": "https://kick.com/pic.webp",
                        }
                    ],
                },
            )
        if request.url.path == "/public/v1/chat":
            payload = json.loads(request.content)
            assert payload == {"type": "user", "broadcaster_user_id": 9001, "content": "hola"}
            assert request.headers["Authorization"] == "Bearer access-1"
            return httpx.Response(200, json={"message": "OK", "data": {"is_sent": True, "message_id": "828f83bb-e391-4c78-9e91-af35a172840e"}})
        if request.url.path == "/oauth/revoke":
            assert request.url.params["token_type_hint"] in {"access_token", "refresh_token"}
            return httpx.Response(200, text="OK")
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = KickClient(settings, http)
        tokens = await client.exchange_authorization_code("code-1", "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")
        identity = await client.get_current_user(tokens.access_token)
        sent = await client.post_user_chat(tokens.access_token, 9001, "hola")
        await client.revoke(tokens.refresh_token or "", "refresh_token")
    assert identity == identity.__class__(user_id=77, username="RealUser")
    assert not hasattr(identity, "email")
    assert sent.is_sent is True
    assert [request.url.path for request in seen] == ["/oauth/token", "/public/v1/users", "/public/v1/chat", "/oauth/revoke"]


def test_state_mismatch_does_not_exchange_code(client) -> None:
    token = create_streamer(client)
    started = client.post(
        "/v1/players/44444444-4444-4444-8444-444444444444/link",
        headers=plugin_headers(token),
        json={"minecraft_username": "Alex", "expiration_seconds": 300},
    )
    code = started.json()["url"].rstrip("/").split("/")[-1]
    redirect = client.get(f"/v1/oauth/start/{code}", follow_redirects=False)
    state = parse_qs(urlparse(redirect.headers["location"]).query)["state"][0]
    bad = client.get("/v1/oauth/callback", params={"code": "stolen", "state": state + "x"})
    assert bad.status_code == 200
    assert "rechazada" in bad.text.lower() or "no coincide" in bad.text.lower()
    assert client.app.state.kick.exchanges == 0
    again = client.get("/v1/oauth/callback", params={"code": "stolen", "state": state})
    assert again.status_code == 200
    assert client.app.state.kick.exchanges == 1


def test_link_is_single_use_and_identity_comes_from_kick(client) -> None:
    token = create_streamer(client)
    player = "11111111-1111-4111-8111-111111111111"
    link_player(client, token, player)
    status = client.get(f"/v1/players/{player}", headers=plugin_headers(token))
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["linked"] is True
    assert body["kick_user_id"] == 4242
    assert body["kick_username"] == "KickPlayer"
    assert "access_token" not in body
    duplicate = client.post(
        f"/v1/players/{player}/link",
        headers=plugin_headers(token),
        json={"minecraft_username": "Steve", "expiration_seconds": 300},
    )
    assert duplicate.status_code == 409
    other = "55555555-5555-4555-8555-555555555555"
    started = client.post(
        f"/v1/players/{other}/link",
        headers=plugin_headers(token),
        json={"minecraft_username": "Alex", "expiration_seconds": 300},
    )
    code = started.json()["url"].rstrip("/").split("/")[-1]
    redirect = client.get(f"/v1/oauth/start/{code}", follow_redirects=False)
    state = parse_qs(urlparse(redirect.headers["location"]).query)["state"][0]
    page = client.get("/v1/oauth/callback", params={"code": "another", "state": state})
    assert "ya está vinculada" in page.text
    accounts = client.get("/v1/admin/streamers/1/accounts", headers=admin_headers())
    assert len(accounts.json()) == 1


def test_expired_link_and_missing_scope(client) -> None:
    token = create_streamer(client)
    started = client.post(
        "/v1/players/66666666-6666-4666-8666-666666666666/link",
        headers=plugin_headers(token),
        json={"minecraft_username": "Steve", "expiration_seconds": 300},
    )
    code = started.json()["url"].rstrip("/").split("/")[-1]
    from app.models import LinkSession
    from app.services.audit import utcnow
    from datetime import timedelta

    db = client.app.state.session_factory()
    try:
        session = db.query(LinkSession).one()
        session.expires_at = utcnow() - timedelta(seconds=5)
        db.commit()
    finally:
        db.close()
    expired = client.get(f"/v1/oauth/start/{code}", follow_redirects=False)
    assert expired.status_code == 410
    client.app.state.kick.scope = "user:read"
    started_again = client.post(
        "/v1/players/66666666-6666-4666-8666-666666666666/link",
        headers=plugin_headers(token),
        json={"minecraft_username": "Steve", "expiration_seconds": 300},
    )
    code = started_again.json()["url"].rstrip("/").split("/")[-1]
    redirect = client.get(f"/v1/oauth/start/{code}", follow_redirects=False)
    state = parse_qs(urlparse(redirect.headers["location"]).query)["state"][0]
    page = client.get("/v1/oauth/callback", params={"code": "limited", "state": state})
    assert "No se pudo vincular" in page.text
    status = client.get(
        "/v1/players/66666666-6666-4666-8666-666666666666",
        headers=plugin_headers(token),
    )
    assert status.json()["linked"] is False
