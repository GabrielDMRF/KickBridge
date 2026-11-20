from __future__ import annotations

from datetime import timedelta

from app.core.config import Settings
from app.database.base import Base
from app.models import KickAccount
from app.services.audit import utcnow
from tests.conftest import FakeKick, admin_headers, create_streamer, link_player, plugin_headers


def _make_client(settings: Settings, fake: FakeKick):
    from fastapi.testclient import TestClient
    from app.core.factory import create_app

    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    app.state.kick = fake
    return TestClient(app)


def test_chat_requires_linked_account(client) -> None:
    token = create_streamer(client)
    res = client.post(
        "/v1/players/11111111-1111-4111-8111-111111111111/chat",
        headers=plugin_headers(token),
        json={"content": "hola"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "not_linked"


def test_chat_sends_as_user_and_validates_content(client) -> None:
    token = create_streamer(client, broadcaster=7777)
    player = "11111111-1111-4111-8111-111111111111"
    link_player(client, token, player)

    res = client.post(
        f"/v1/players/{player}/chat",
        headers=plugin_headers(token),
        json={"content": "Hola desde Minecraft!"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["sent"] is True
    assert res.json()["message_id"] == "828f83bb-e391-4c78-9e91-af35a172840e"
    assert len(client.app.state.kick.chat_calls) == 1
    assert client.app.state.kick.chat_calls[0] == {
        "access_token": "access-player-token",
        "broadcaster_user_id": 7777,
        "content": "Hola desde Minecraft!",
        "type": "user",
    }

    too_long = client.post(
        f"/v1/players/{player}/chat",
        headers=plugin_headers(token),
        json={"content": "a" * 501},
    )
    assert too_long.status_code == 400
    assert too_long.json()["error"]["code"] == "message_too_long"

    control_char = client.post(
        f"/v1/players/{player}/chat",
        headers=plugin_headers(token),
        json={"content": "hola\x00mundo"},
    )
    assert control_char.status_code == 400
    assert control_char.json()["error"]["code"] == "invalid_message"


def test_chat_refreshes_expired_token_automatically(client) -> None:
    token = create_streamer(client)
    player = "11111111-1111-4111-8111-111111111111"
    link_player(client, token, player)

    db = client.app.state.session_factory()
    try:
        acc = db.query(KickAccount).one()
        acc.access_expires_at = utcnow() - timedelta(seconds=10)
        db.commit()
    finally:
        db.close()

    res = client.post(
        f"/v1/players/{player}/chat",
        headers=plugin_headers(token),
        json={"content": "Con token renovado"},
    )
    assert res.status_code == 200, res.text
    assert client.app.state.kick.refresh_calls == 1
    assert client.app.state.kick.chat_calls[-1]["access_token"] == "access-refreshed-token"


def test_chat_403_does_not_fallback_to_bot(client) -> None:
    token = create_streamer(client)
    player = "11111111-1111-4111-8111-111111111111"
    link_player(client, token, player)

    client.app.state.kick.fail_chat_status = 403
    res = client.post(
        f"/v1/players/{player}/chat",
        headers=plugin_headers(token),
        json={"content": "Mensaje bloqueado"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "kick_forbidden"
    assert len(client.app.state.kick.chat_calls) == 1


def test_chat_cooldown_and_rate_limit(settings: Settings, fake: FakeKick) -> None:
    strict = settings.model_copy(update={"chat_cooldown_seconds": 10, "chat_rate_limit": 2, "chat_rate_window_seconds": 60})
    with _make_client(strict, fake) as client:
        token = create_streamer(client)
        player = "11111111-1111-4111-8111-111111111111"
        link_player(client, token, player)

        first = client.post(f"/v1/players/{player}/chat", headers=plugin_headers(token), json={"content": "Uno"})
        assert first.status_code == 200

        second = client.post(f"/v1/players/{player}/chat", headers=plugin_headers(token), json={"content": "Dos"})
        assert second.status_code == 429
        assert second.json()["error"]["code"] == "cooldown"
        assert "Retry-After" in second.headers


def test_chat_rate_limit_window(settings: Settings, fake: FakeKick) -> None:
    windowed = settings.model_copy(update={"chat_cooldown_seconds": 0, "chat_rate_limit": 2, "chat_rate_window_seconds": 60})
    with _make_client(windowed, fake) as client:
        token = create_streamer(client)
        player = "11111111-1111-4111-8111-111111111111"
        link_player(client, token, player)

        for msg in ("Uno", "Dos"):
            ok = client.post(f"/v1/players/{player}/chat", headers=plugin_headers(token), json={"content": msg})
            assert ok.status_code == 200

        limited = client.post(f"/v1/players/{player}/chat", headers=plugin_headers(token), json={"content": "Tres"})
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limited"


def test_unlink_revokes_tokens_and_blocks_subsequent_chat(client) -> None:
    token = create_streamer(client)
    player = "11111111-1111-4111-8111-111111111111"
    link_player(client, token, player)

    unlinked = client.delete(f"/v1/players/{player}", headers=plugin_headers(token))
    assert unlinked.status_code == 200
    assert unlinked.json()["unlinked"] is True
    assert ("refresh_token", "refresh-player-token") in client.app.state.kick.revoked

    denied = client.post(f"/v1/players/{player}/chat", headers=plugin_headers(token), json={"content": "hola"})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "not_linked"


def test_admin_stats_and_token_rotation(client) -> None:
    token = create_streamer(client, name="StreamerA", broadcaster=500)
    player = "11111111-1111-4111-8111-111111111111"
    link_player(client, token, player)
    client.post(f"/v1/players/{player}/chat", headers=plugin_headers(token), json={"content": "Hola"})

    stats = client.get("/v1/admin/streamers/1/stats", headers=admin_headers())
    assert stats.status_code == 200
    assert stats.json()["linked_accounts"] == 1
    assert stats.json()["messages_sent"] == 1

    rotated = client.post("/v1/admin/streamers/1/rotate-token", headers=admin_headers())
    assert rotated.status_code == 200
    new_token = rotated.json()["api_token"]
    assert new_token != token

    old_denied = client.get(f"/v1/players/{player}", headers=plugin_headers(token))
    assert old_denied.status_code == 401
    new_ok = client.get(f"/v1/players/{player}", headers=plugin_headers(new_token))
    assert new_ok.status_code == 200
