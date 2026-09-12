"""Vehicle login client and single-flight token management for VOGE."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout

from .api import VogeApiError, VogeAuthError
from .const import (
    AUTH_MODE_PASSWORD,
    CONF_TOKEN,
    MODERN_BASE_URL,
    VERSION,
)
from .util import parse_int

LOGIN_PATH = "/api/login/loginByMobile"
LOGIN_ENDPOINT = "auth.login"


class _TokenClient(Protocol):
    def set_token(self, token: str) -> None:
        """Update the token used by a data client."""


async def _read_limited(response: ClientResponse, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.content.iter_chunked(65_536):
        size += len(chunk)
        if size > limit:
            raise VogeAuthError(LOGIN_ENDPOINT, "response_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def md5_password(password: str) -> str:
    """Return the lowercase UTF-8 MD5 representation expected by the service."""
    if not isinstance(password, str) or not password:
        raise ValueError("A non-empty password is required")
    return hashlib.md5(password.encode("utf-8"), usedforsecurity=False).hexdigest()


class VogeAuthClient:
    """Restricted client for the fixed vehicle login request."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def login(self, mobile: str, password: str) -> str:
        """Log in to the modern vehicle API and return only its access token."""
        if not isinstance(mobile, str) or not mobile.strip():
            raise VogeAuthError(LOGIN_ENDPOINT, "invalid_mobile")
        if not isinstance(password, str) or not password:
            raise VogeAuthError(LOGIN_ENDPOINT, "invalid_password")

        body = {
            "mobile": mobile.strip(),
            "password": md5_password(password),
        }
        headers = {
            "Content-Type": "application/json",
            "Content-Language": "zh_CN",
            "Platform": "ANDROID",
            "Mansuoid": "",
            "Blade-Auth": "",
            "version": VERSION,
            "PhoneModel": "HomeAssistant/voge-0.1.0",
            "Source": "VOGE",
        }
        try:
            async with self._session.post(
                f"{MODERN_BASE_URL}{LOGIN_PATH}",
                data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8"
                ),
                headers=headers,
                timeout=ClientTimeout(total=30),
                allow_redirects=False,
            ) as response:
                if response.status == 401:
                    raise VogeAuthError(LOGIN_ENDPOINT, "authentication_failed", status=401)
                if response.status == 429:
                    raise VogeApiError(LOGIN_ENDPOINT, "rate_limited", status=429)
                if 300 <= response.status < 400:
                    raise VogeAuthError(
                        LOGIN_ENDPOINT,
                        "redirect_rejected",
                        status=response.status,
                    )
                if response.status >= 400:
                    raise VogeApiError(LOGIN_ENDPOINT, "http_error", status=response.status)
                raw = await _read_limited(response, 2 * 1024 * 1024)
        except (VogeApiError, VogeAuthError):
            raise
        except (ClientError, TimeoutError) as err:
            raise VogeApiError(LOGIN_ENDPOINT, "transport_error") from err

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            raise VogeAuthError(LOGIN_ENDPOINT, "invalid_json") from err
        if not isinstance(payload, dict):
            raise VogeAuthError(LOGIN_ENDPOINT, "response_not_object")

        code = parse_int(payload.get("code"))
        if code == 401:
            raise VogeAuthError(LOGIN_ENDPOINT, "authentication_failed", code=401)
        if code != 200:
            raise VogeAuthError(LOGIN_ENDPOINT, "login_rejected", code=code)
        if payload.get("success") is False:
            raise VogeAuthError(LOGIN_ENDPOINT, "login_rejected", code=code)

        result = payload.get("result")
        if not isinstance(result, dict):
            raise VogeAuthError(LOGIN_ENDPOINT, "token_missing")
        token = result.get("token")
        if not isinstance(token, str) or not token.strip():
            raise VogeAuthError(LOGIN_ENDPOINT, "token_missing")
        return token.strip()


class VogeAuthManager:
    """Keep one account token current and serialize password logins."""

    def __init__(
        self,
        hass: Any,
        entry: Any,
        session: ClientSession,
        *,
        mode: str,
        token: str | None,
        mobile: str | None,
        password: str | None,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._client = VogeAuthClient(session)
        self.mode = mode
        self._token = token.strip() if isinstance(token, str) else ""
        self._mobile = mobile.strip() if isinstance(mobile, str) else None
        self._password = password if isinstance(password, str) else None
        self._lock = asyncio.Lock()
        self._clients: list[_TokenClient] = []
        self._closed = False

    @property
    def token(self) -> str:
        """Return the current in-memory access token."""
        return self._token

    @property
    def has_password(self) -> bool:
        """Return whether automatic password login is configured."""
        return bool(self._mobile and self._password)

    def register_client(self, client: _TokenClient) -> None:
        """Register a data client that must receive rotated tokens."""
        if self._closed:
            raise RuntimeError("VOGE authentication manager is closed")
        client.set_token(self._token)
        self._clients.append(client)

    async def async_authenticate(
        self,
        observed_token: str | None = None,
        *,
        force: bool = False,
    ) -> str:
        """Reuse a newer token or perform one serialized password login."""
        async with self._lock:
            if self._closed:
                raise VogeAuthError(LOGIN_ENDPOINT, "manager_closed")
            if observed_token is not None and self._token != observed_token:
                return self._token
            if observed_token is None and self._token and not force:
                return self._token
            if self.mode != AUTH_MODE_PASSWORD or not self.has_password:
                raise VogeAuthError(LOGIN_ENDPOINT, "credentials_unavailable")

            # Keep the password local to this call; never pass it to logging or errors.
            mobile = self._mobile
            password = self._password
            if mobile is None or password is None:
                raise VogeAuthError(LOGIN_ENDPOINT, "credentials_unavailable")
            token = await self._client.login(mobile, password)
            self._set_token(token)
            data = dict(self._entry.data)
            data[CONF_TOKEN] = token
            self._hass.config_entries.async_update_entry(self._entry, data=data)
            return token

    def _set_token(self, token: str) -> None:
        if not token:
            raise VogeAuthError(LOGIN_ENDPOINT, "token_missing")
        self._token = token
        for client in self._clients:
            client.set_token(token)

    def close(self) -> None:
        """Release references to credentials when the config entry unloads."""
        self._closed = True
        self._password = None
        self._mobile = None
        self._clients.clear()


AuthFailureHandler = Callable[[str], Awaitable[Any]]
