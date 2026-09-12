"""Synthetic tests for VOGE vehicle authentication and token recovery."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.voge.api import VogeModernClient
from custom_components.voge.auth_manager import (
    AUTH_MODE_PASSWORD,
    VogeAuthClient,
    VogeAuthManager,
    md5_password,
)


class _Content:
    def __init__(self, body: bytes) -> None:
        self._body = body

    async def iter_chunked(self, size: int):
        for offset in range(0, len(self._body), size):
            yield self._body[offset : offset + size]


class _Response:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self.headers: dict[str, str] = {}
        self.content = _Content(json.dumps(payload).encode("utf-8"))


class _ContextManager:
    def __init__(self, response: _Response) -> None:
        self.response = response

    async def __aenter__(self) -> _Response:
        return self.response

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class _PostSession:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _ContextManager:
        self.calls.append({"url": url, **kwargs})
        return _ContextManager(self.response)


class _GetSession:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> _ContextManager:
        self.calls.append({"url": url, **kwargs})
        return _ContextManager(self.responses.pop(0))


class _ConfigEntries:
    def __init__(self) -> None:
        self.updated: list[tuple[Any, dict[str, Any]]] = []

    def async_update_entry(self, entry: Any, *, data: dict[str, Any]) -> None:
        self.updated.append((entry, data))


class _Hass:
    def __init__(self) -> None:
        self.config_entries = _ConfigEntries()


class _Entry:
    def __init__(self) -> None:
        self.data = {"token": "old-token"}


def test_md5_password_uses_lowercase_utf8_without_trimming() -> None:
    assert md5_password("pässword") == "8e1843033a0f6ee52e2f618aa8ebbef4"
    assert md5_password(" secret ") == "320bb1d43ec042096a83dbac6dc9294a"


def test_login_uses_fixed_vehicle_endpoint_and_only_expected_fields() -> None:
    session = _PostSession(
        _Response(
            200,
            {"code": 200, "success": True, "result": {"token": "new-token"}},
        )
    )
    token = asyncio.run(
        VogeAuthClient(session).login("13800000000", "secret")  # type: ignore[arg-type]
    )
    assert token == "new-token"
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == "https://iot-api.loncinindustries.com/api/login/loginByMobile"
    assert call["allow_redirects"] is False
    assert call["headers"]["Content-Type"] == "application/json"
    body = json.loads(call["data"])
    assert set(body) == {"mobile", "password"}
    assert body["mobile"] == "13800000000"
    assert body["password"] == md5_password("secret")


def test_login_rejects_malformed_response_without_secret_in_error() -> None:
    session = _PostSession(_Response(200, {"code": 200, "result": {}}))
    with pytest.raises(Exception) as raised:
        asyncio.run(
            VogeAuthClient(session).login("13800000000", "secret")  # type: ignore[arg-type]
        )
    text = str(raised.value)
    assert "secret" not in text
    assert "13800000000" not in text
    assert "token_missing" in text


def test_modern_client_retries_one_get_after_401_with_updated_token() -> None:
    session = _GetSession(
        [
            _Response(401, {}),
            _Response(200, {"code": 200, "result": [{"deviceId": "device"}]}),
        ]
    )
    client: VogeModernClient

    async def recover(observed_token: str) -> str:
        assert observed_token == "old-token"
        client.set_token("new-token")
        return "new-token"

    client = VogeModernClient(session, "old-token", recover)  # type: ignore[arg-type]
    assert asyncio.run(client.get_devices()) == [{"deviceId": "device"}]
    assert len(session.calls) == 2
    assert session.calls[0]["headers"]["Mansuoid"] == "old-token"
    assert session.calls[1]["headers"]["Mansuoid"] == "new-token"


def test_auth_manager_single_flight_reuses_one_login() -> None:
    manager = VogeAuthManager(
        _Hass(),
        _Entry(),
        _PostSession(_Response(200, {})),  # type: ignore[arg-type]
        mode=AUTH_MODE_PASSWORD,
        token="old-token",
        mobile="13800000000",
        password="secret",
    )
    manager._client.login = AsyncMock(return_value="new-token")  # type: ignore[method-assign]

    async def run() -> tuple[str, str, str]:
        return await asyncio.gather(
            manager.async_authenticate("old-token"),
            manager.async_authenticate("old-token"),
            manager.async_authenticate("old-token"),
        )

    assert asyncio.run(run()) == ["new-token", "new-token", "new-token"]
    manager._client.login.assert_awaited_once_with("13800000000", "secret")


def test_token_only_manager_does_not_attempt_unconfirmed_refresh() -> None:
    manager = VogeAuthManager(
        _Hass(),
        _Entry(),
        _PostSession(_Response(200, {})),  # type: ignore[arg-type]
        mode="token",
        token="old-token",
        mobile=None,
        password=None,
    )
    with pytest.raises(Exception) as raised:
        asyncio.run(manager.async_authenticate("old-token"))
    assert "credentials_unavailable" in str(raised.value)
    assert "club-auth" not in str(raised.value)
    assert "gateway.do" not in str(raised.value)
