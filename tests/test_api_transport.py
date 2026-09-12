"""Synthetic transport tests; no production endpoint is contacted."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from custom_components.voge import api as api_module
from custom_components.voge.api import (
    ReadOnlyViolation,
    VogeApiError,
    VogeAuthError,
    VogeModernClient,
)


class _Content:
    def __init__(self, body: bytes) -> None:
        self._body = body

    async def iter_chunked(self, size: int):
        for offset in range(0, len(self._body), size):
            yield self._body[offset : offset + size]


class _Response:
    def __init__(
        self,
        status: int,
        payload: Any,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.headers = headers or {}
        self.content = _Content(json.dumps(payload).encode())


class _ContextManager:
    def __init__(self, response: _Response) -> None:
        self.response = response

    async def __aenter__(self) -> _Response:
        return self.response

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class _Session:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> _ContextManager:
        self.calls.append({"url": url, **kwargs})
        return _ContextManager(self.response)


def test_modern_transport_is_get_only_and_rejects_redirect_following() -> None:
    session = _Session(_Response(200, {"code": 200, "result": [{"deviceId": "d"}]}))
    client = VogeModernClient(session, "private-token")  # type: ignore[arg-type]
    result = asyncio.run(client.get_devices())
    assert result == [{"deviceId": "d"}]
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == "https://iot-api.loncinindustries.com/api/app/favorite/device"
    assert call["allow_redirects"] is False
    assert call["params"] == {}
    assert call["headers"]["Mansuoid"] == "private-token"
    assert call["headers"]["Blade-Auth"] == ""


def test_body_level_401_raises_diagnostic_safe_auth_error() -> None:
    session = _Session(_Response(200, {"code": 401, "message": "expired"}))
    client = VogeModernClient(session, "private-token")  # type: ignore[arg-type]
    with pytest.raises(VogeAuthError) as raised:
        asyncio.run(client.get_devices())
    text = str(raised.value)
    assert "modern.devices" in text
    assert "private-token" not in text
    assert "iot-api" not in text


def test_http_redirect_is_rejected_without_reading_destination() -> None:
    session = _Session(_Response(302, {}))
    client = VogeModernClient(session, "private-token")  # type: ignore[arg-type]
    with pytest.raises(ReadOnlyViolation, match="redirect_rejected"):
        asyncio.run(client.get_devices())
    assert len(session.calls) == 1


def test_http_429_honors_retry_after_without_immediate_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [100.0]
    monkeypatch.setattr(api_module, "monotonic", lambda: clock[0])
    session = _Session(_Response(429, {}, headers={"Retry-After": "120"}))
    client = VogeModernClient(session, "private-token")  # type: ignore[arg-type]

    with pytest.raises(VogeApiError, match="rate_limited"):
        asyncio.run(client.get_devices())
    assert len(session.calls) == 1

    session.response = _Response(200, {"code": 200, "result": []})
    with pytest.raises(VogeApiError, match="rate_limit_cooldown"):
        asyncio.run(client.get_devices())
    assert len(session.calls) == 1

    clock[0] = 221.0
    assert asyncio.run(client.get_devices()) == []
    assert len(session.calls) == 2


def test_body_429_uses_bounded_fallback_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [500.0]
    monkeypatch.setattr(api_module, "monotonic", lambda: clock[0])
    session = _Session(_Response(200, {"code": 429, "message": "slow down"}))
    client = VogeModernClient(session, "private-token")  # type: ignore[arg-type]

    with pytest.raises(VogeApiError, match="rate_limited"):
        asyncio.run(client.get_devices())
    session.response = _Response(200, {"code": 200, "result": []})

    clock[0] = 529.0
    with pytest.raises(VogeApiError, match="rate_limit_cooldown"):
        asyncio.run(client.get_devices())
    assert len(session.calls) == 1

    clock[0] = 531.0
    assert asyncio.run(client.get_devices()) == []
    assert len(session.calls) == 2
