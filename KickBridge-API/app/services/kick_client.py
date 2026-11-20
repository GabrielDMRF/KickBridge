from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import OAUTH_SCOPES, USER_CHAT_TYPE, Settings


class KickRequestError(Exception):
    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(f"kick_http_{status}")


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str | None
    expires_in: int
    refresh_expires_in: int | None
    scope: str


@dataclass(frozen=True)
class KickIdentity:
    user_id: int
    username: str


@dataclass(frozen=True)
class ChatSendResult:
    message_id: str | None
    is_sent: bool


class KickClient:
    """Cliente de la API pública de Kick. El chat solo se envía como type=user."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        self._owns_http = http is None
        self._app_token: str | None = None
        self._app_exp_monotonic: float = 0.0

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    def authorize_url(self, *, state: str, code_challenge: str) -> str:
        from urllib.parse import urlencode

        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.settings.kick_client_id,
                "redirect_uri": self.settings.kick_redirect_uri,
                "scope": OAUTH_SCOPES,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "state": state,
            }
        )
        return f"{self.settings.kick_oauth_base}/oauth/authorize?{query}"

    async def exchange_authorization_code(self, code: str, code_verifier: str) -> TokenSet:
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.settings.kick_client_id,
            "client_secret": self.settings.kick_client_secret,
            "redirect_uri": self.settings.kick_redirect_uri,
            "code": code,
            "code_verifier": code_verifier,
        }
        return await self._token(payload, require_refresh=True)

    async def refresh(self, refresh_token: str) -> TokenSet:
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.settings.kick_client_id,
            "client_secret": self.settings.kick_client_secret,
            "refresh_token": refresh_token,
        }
        return await self._token(payload, require_refresh=False)

    async def revoke(self, token: str, hint: str) -> None:
        # OpenAPI usa token_type_hint (RFC 7009). La guía en markdown nombra token_hint_type.
        try:
            await self._http.post(
                f"{self.settings.kick_oauth_base}/oauth/revoke",
                params={"token": token, "token_type_hint": hint},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError:
            return

    async def get_current_user(self, access_token: str) -> KickIdentity:
        response = await self._api("GET", "/public/v1/users", access_token)
        data = response.get("data")
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise KickRequestError(502)
        user = data[0]
        user_id = user.get("user_id")
        name = user.get("name")
        if not isinstance(user_id, int) or user_id <= 0 or not isinstance(name, str) or not name.strip():
            raise KickRequestError(502)
        return KickIdentity(user_id=user_id, username=name.strip()[:64])

    async def post_user_chat(self, access_token: str, broadcaster_user_id: int, content: str) -> ChatSendResult:
        if broadcaster_user_id <= 0:
            raise KickRequestError(400)
        body = build_user_chat_body(broadcaster_user_id, content)
        response = await self._api("POST", "/public/v1/chat", access_token, json_body=body)
        data = response.get("data") if isinstance(response, dict) else None
        if not isinstance(data, dict):
            raise KickRequestError(502)
        is_sent = bool(data.get("is_sent"))
        message_id = data.get("message_id")
        if message_id is not None and not isinstance(message_id, str):
            message_id = None
        return ChatSendResult(message_id=message_id, is_sent=is_sent)

    async def resolve_channel_slug(self, slug: str) -> tuple[int, str]:
        token = await self._app_access_token()
        response = await self._api("GET", "/public/v1/channels", token, params={"slug": slug})
        data = response.get("data")
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise KickRequestError(404)
        channel = data[0]
        broadcaster_id = channel.get("broadcaster_user_id")
        found_slug = channel.get("slug") or slug
        if not isinstance(broadcaster_id, int) or broadcaster_id <= 0:
            raise KickRequestError(502)
        return broadcaster_id, str(found_slug)[:25]

    async def _app_access_token(self) -> str:
        import time

        if self._app_token and time.monotonic() < self._app_exp_monotonic:
            return self._app_token
        tokens = await self._token(
            {
                "grant_type": "client_credentials",
                "client_id": self.settings.kick_client_id,
                "client_secret": self.settings.kick_client_secret,
            },
            require_refresh=False,
        )
        self._app_token = tokens.access_token
        self._app_exp_monotonic = time.monotonic() + max(30, tokens.expires_in - 60)
        return tokens.access_token

    async def _token(self, payload: dict[str, str], *, require_refresh: bool) -> TokenSet:
        try:
            response = await self._http.post(
                f"{self.settings.kick_oauth_base}/oauth/token",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise KickRequestError(503) from exc
        if response.status_code != 200:
            raise KickRequestError(response.status_code)
        try:
            body = response.json()
        except ValueError as exc:
            raise KickRequestError(502) from exc
        access = body.get("access_token")
        if not isinstance(access, str) or not access:
            raise KickRequestError(502)
        refresh = body.get("refresh_token")
        if require_refresh and (not isinstance(refresh, str) or not refresh):
            raise KickRequestError(502)
        if refresh is not None and not isinstance(refresh, str):
            refresh = None
        expires_in = body.get("expires_in")
        if not isinstance(expires_in, int) or expires_in <= 0:
            raise KickRequestError(502)
        refresh_expires = body.get("refresh_expires_in")
        if refresh_expires is not None and not isinstance(refresh_expires, int):
            refresh_expires = None
        scope = body.get("scope") if isinstance(body.get("scope"), str) else ""
        return TokenSet(
            access_token=access,
            refresh_token=refresh,
            expires_in=expires_in,
            refresh_expires_in=refresh_expires,
            scope=scope,
        )

    async def _api(
        self,
        method: str,
        path: str,
        access_token: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        try:
            response = await self._http.request(
                method,
                f"{self.settings.kick_api_base}{path}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=json_body,
                params=params,
            )
        except httpx.HTTPError as exc:
            raise KickRequestError(503) from exc
        if response.status_code not in {200, 204}:
            raise KickRequestError(response.status_code)
        if response.status_code == 204 or not response.content:
            return {}
        try:
            body = response.json()
        except ValueError as exc:
            raise KickRequestError(502) from exc
        if not isinstance(body, dict):
            raise KickRequestError(502)
        return body


def build_user_chat_body(broadcaster_user_id: int, content: str) -> dict:
    if USER_CHAT_TYPE != "user":
        raise RuntimeError("El tipo de chat dejó de ser user")
    return {
        "type": USER_CHAT_TYPE,
        "broadcaster_user_id": int(broadcaster_user_id),
        "content": content,
    }


def scopes_allow_chat(scope: str) -> bool:
    granted = set(scope.split())
    return "user:read" in granted and "chat:write" in granted
