"""Strictly allowlisted read-only clients for VOGE cloud APIs."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import ceil
from time import monotonic
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout

from .auth import LegacyApplicationCredentials, build_legacy_headers
from .const import (
    LEGACY_BASE_URL,
    LEGACY_MAX_BODY_BYTES,
    MODERN_BASE_URL,
    MODERN_MAX_BODY_BYTES,
    RATE_LIMIT_FALLBACK_SECONDS,
    RATE_LIMIT_MAX_SECONDS,
    ROUTE_MAX_BODY_BYTES,
    ROUTE_TIMEOUT_SECONDS,
    TIMEOUT_SECONDS,
)
from .util import parse_int

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _parse_retry_after(value: str | None) -> int | None:
    """Parse and clamp Retry-After without ever sleeping inside a request."""
    if not isinstance(value, str) or not (value := value.strip()):
        return None
    if value.isdecimal():
        seconds = int(value)
    else:
        try:
            target = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if target is None:
            return None
        if target.tzinfo is None:
            target = target.replace(tzinfo=UTC)
        seconds = ceil((target.astimezone(UTC) - datetime.now(UTC)).total_seconds())
    return min(max(seconds, 1), RATE_LIMIT_MAX_SECONDS)


class VogeApiError(Exception):
    """A diagnostic-safe VOGE API error."""

    def __init__(
        self,
        endpoint: str,
        reason: str,
        *,
        status: int | None = None,
        code: int | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.reason = reason
        self.status = status
        self.code = code
        details = [endpoint, reason]
        if status is not None:
            details.append(f"http={status}")
        if code is not None:
            details.append(f"code={code}")
        super().__init__("; ".join(details))


class VogeAuthError(VogeApiError):
    """Raised for HTTP or body-level authentication failure."""


class ReadOnlyViolation(VogeApiError):
    """Raised before a request that is not explicitly allowed."""


@dataclass(frozen=True, slots=True)
class Endpoint:
    """A compile-time read-only endpoint declaration."""

    name: str
    base_url: str
    path: str
    query_keys: frozenset[str]
    modern: bool
    max_body_bytes: int
    timeout_seconds: int = TIMEOUT_SECONDS


M_DEVICES = Endpoint(
    "modern.devices",
    MODERN_BASE_URL,
    "/api/app/favorite/device",
    frozenset(),
    True,
    MODERN_MAX_BODY_BYTES,
)
M_DIAGNOSIS = Endpoint(
    "modern.diagnosis",
    MODERN_BASE_URL,
    "/api/app/favorite/synthesize-diagnosis",
    frozenset(),
    True,
    MODERN_MAX_BODY_BYTES,
)
M_MONTH_INDEX = Endpoint(
    "modern.month_index",
    MODERN_BASE_URL,
    "/api/app/favorite/index",
    frozenset({"deviceId"}),
    True,
    MODERN_MAX_BODY_BYTES,
)
M_MONTH_TRACKS = Endpoint(
    "modern.month_tracks",
    MODERN_BASE_URL,
    "/api/app/favorite/car-track-new",
    frozenset({"deviceId", "month"}),
    True,
    MODERN_MAX_BODY_BYTES,
)
M_ROUTE_DETAIL = Endpoint(
    "modern.route_detail",
    MODERN_BASE_URL,
    "/api/app/favorite/locus",
    frozenset({"routeId"}),
    True,
    ROUTE_MAX_BODY_BYTES,
    ROUTE_TIMEOUT_SECONDS,
)
M_BEHAVIOR = Endpoint(
    "modern.behavior",
    MODERN_BASE_URL,
    "/api/app/favorite/behavior",
    frozenset({"deviceId", "month"}),
    True,
    MODERN_MAX_BODY_BYTES,
)
M_RIDING = Endpoint(
    "modern.riding",
    MODERN_BASE_URL,
    "/api/app/favorite/riding",
    frozenset({"deviceId", "month"}),
    True,
    MODERN_MAX_BODY_BYTES,
)
M_FUNCTION_CONFIG = Endpoint(
    "modern.function_config",
    MODERN_BASE_URL,
    "/api/app/operateConfig/getConfigCodes",
    frozenset(),
    True,
    MODERN_MAX_BODY_BYTES,
)
L_MESSAGES = Endpoint(
    "legacy.messages",
    LEGACY_BASE_URL,
    "/voge-system/app/message/page",
    frozenset({"module", "pageSize", "pageNum"}),
    False,
    LEGACY_MAX_BODY_BYTES,
)
L_MESSAGE_INFO = Endpoint(
    "legacy.message_info",
    LEGACY_BASE_URL,
    "/voge-system/app/message/info",
    frozenset({"messageId"}),
    False,
    LEGACY_MAX_BODY_BYTES,
)
L_VEHICLES = Endpoint(
    "legacy.vehicles",
    LEGACY_BASE_URL,
    "/moto/app/vehicle/excludeShareVehicle",
    frozenset(),
    False,
    LEGACY_MAX_BODY_BYTES,
)

_ALLOWED_ENDPOINTS = frozenset(
    {
        M_DEVICES,
        M_DIAGNOSIS,
        M_MONTH_INDEX,
        M_MONTH_TRACKS,
        M_ROUTE_DETAIL,
        M_BEHAVIOR,
        M_RIDING,
        M_FUNCTION_CONFIG,
        L_MESSAGES,
        L_MESSAGE_INFO,
        L_VEHICLES,
    }
)


def _validate_identifier(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ReadOnlyViolation("local.validation", f"{field}_not_string")
    stripped = value.strip()
    if not stripped or len(stripped) > 256 or any(char in stripped for char in "\r\n"):
        raise ReadOnlyViolation("local.validation", f"invalid_{field}")
    return stripped


def _validate_month(month: str) -> str:
    if not isinstance(month, str) or not _MONTH_RE.fullmatch(month):
        raise ReadOnlyViolation("local.validation", "invalid_month")
    return month


def _validate_request(endpoint: Endpoint, params: dict[str, Any]) -> None:
    """Reject any endpoint or query shape outside the static allowlist."""
    if endpoint not in _ALLOWED_ENDPOINTS:
        raise ReadOnlyViolation(endpoint.name, "endpoint_not_allowlisted")
    if frozenset(params) != endpoint.query_keys:
        raise ReadOnlyViolation(endpoint.name, "query_keys_not_allowlisted")
    if not endpoint.base_url.startswith("https://"):
        raise ReadOnlyViolation(endpoint.name, "non_tls_endpoint")
    if not endpoint.path.startswith("/") or ".." in endpoint.path:
        raise ReadOnlyViolation(endpoint.name, "invalid_path")


async def _read_limited(response: ClientResponse, limit: int, endpoint: str) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.content.iter_chunked(65_536):
        size += len(chunk)
        if size > limit:
            raise VogeApiError(endpoint, "response_too_large", status=response.status)
        chunks.append(chunk)
    return b"".join(chunks)


AuthFailureHandler = Callable[[str], Awaitable[Any]]


class _BaseReadOnlyClient:
    """Shared transport with no arbitrary-method escape hatch."""

    def __init__(
        self,
        session: ClientSession,
        token: str,
        auth_failure_handler: AuthFailureHandler | None = None,
    ) -> None:
        token = token.strip()
        if not token:
            raise ValueError("A non-empty VOGE token is required")
        self._session = session
        self._token = token
        self._auth_failure_handler = auth_failure_handler
        self._rate_limit_failures = 0
        self._rate_limit_not_before = 0.0

    def set_token(self, token: str) -> None:
        """Update the token without exposing a general request escape hatch."""
        token = token.strip()
        if not token:
            raise ValueError("A non-empty VOGE token is required")
        self._token = token

    def _activate_rate_limit(self, retry_after: str | None) -> None:
        self._rate_limit_failures += 1
        exponent = min(self._rate_limit_failures - 1, 16)
        fallback = min(
            RATE_LIMIT_FALLBACK_SECONDS * (2**exponent),
            RATE_LIMIT_MAX_SECONDS,
        )
        delay = _parse_retry_after(retry_after) or fallback
        self._rate_limit_not_before = max(
            self._rate_limit_not_before,
            monotonic() + delay,
        )

    def _check_rate_limit(self, endpoint: Endpoint) -> None:
        if monotonic() < self._rate_limit_not_before:
            raise VogeApiError(endpoint.name, "rate_limit_cooldown", status=429)

    def _clear_rate_limit(self) -> None:
        self._rate_limit_failures = 0
        self._rate_limit_not_before = 0.0

    async def _get(
        self,
        endpoint: Endpoint,
        params: dict[str, Any],
        headers: dict[str, str] | Callable[[], dict[str, str]],
        *,
        allow_auth_retry: bool = True,
    ) -> Any:
        _validate_request(endpoint, params)
        self._check_rate_limit(endpoint)
        observed_token = self._token
        try:
            return await self._get_once(endpoint, params, headers)
        except VogeAuthError:
            if not allow_auth_retry or self._auth_failure_handler is None:
                raise
            await self._auth_failure_handler(observed_token)
            return await self._get(
                endpoint,
                params,
                headers,
                allow_auth_retry=False,
            )

    async def _get_once(
        self,
        endpoint: Endpoint,
        params: dict[str, Any],
        headers: dict[str, str] | Callable[[], dict[str, str]],
    ) -> Any:
        request_headers = headers() if callable(headers) else headers
        url = f"{endpoint.base_url}{endpoint.path}"
        timeout = ClientTimeout(total=endpoint.timeout_seconds)
        try:
            async with self._session.get(
                url,
                params=params,
                headers=request_headers,
                timeout=timeout,
                allow_redirects=False,
            ) as response:
                if response.status == 429:
                    self._activate_rate_limit(response.headers.get("Retry-After"))
                    raise VogeApiError(endpoint.name, "rate_limited", status=429)
                if response.status == 401:
                    raise VogeAuthError(endpoint.name, "authentication_failed", status=401)
                if 300 <= response.status < 400:
                    raise ReadOnlyViolation(endpoint.name, "redirect_rejected", status=response.status)
                if response.status >= 400:
                    raise VogeApiError(endpoint.name, "http_error", status=response.status)
                raw = await _read_limited(response, endpoint.max_body_bytes, endpoint.name)
        except VogeApiError:
            raise
        except (ClientError, TimeoutError) as err:
            raise VogeApiError(endpoint.name, "transport_error") from err

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            raise VogeApiError(endpoint.name, "invalid_json") from err
        if not isinstance(payload, dict):
            raise VogeApiError(endpoint.name, "response_not_object")
        result = self._unwrap(endpoint, payload)
        self._clear_rate_limit()
        return result

    def _unwrap(self, endpoint: Endpoint, payload: dict[str, Any]) -> Any:
        code = parse_int(payload.get("code"))
        success_code = 200 if endpoint.modern else 0
        if code == 429:
            self._activate_rate_limit(None)
            raise VogeApiError(endpoint.name, "rate_limited", code=429)
        if code == 401:
            raise VogeAuthError(endpoint.name, "authentication_failed", code=401)
        if code != success_code:
            raise VogeApiError(endpoint.name, "business_error", code=code)
        key = "result" if endpoint.modern else "data"
        return payload.get(key)


class VogeModernClient(_BaseReadOnlyClient):
    """Allowlisted modern VOGE vehicle client."""

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Language": "zh_CN",
            "Platform": "ANDROID",
            "Mansuoid": self._token,
            "Blade-Auth": "",
            "version": "1.3.3",
            "PhoneModel": "HomeAssistant/voge-0.1.0",
            "Source": "VOGE",
        }

    async def get_devices(self) -> Any:
        return await self._get(M_DEVICES, {}, self._headers)

    async def get_diagnosis(self) -> Any:
        return await self._get(M_DIAGNOSIS, {}, self._headers)

    async def get_month_index(self, device_id: str) -> Any:
        device_id = _validate_identifier(device_id, "device_id")
        return await self._get(M_MONTH_INDEX, {"deviceId": device_id}, self._headers)

    async def get_month_tracks(self, device_id: str, month: str) -> Any:
        device_id = _validate_identifier(device_id, "device_id")
        month = _validate_month(month)
        return await self._get(
            M_MONTH_TRACKS,
            {"deviceId": device_id, "month": month},
            self._headers,
        )

    async def get_route_detail(self, route_id: str) -> Any:
        route_id = _validate_identifier(route_id, "route_id")
        return await self._get(M_ROUTE_DETAIL, {"routeId": route_id}, self._headers)

    async def get_behavior(self, device_id: str, month: str) -> Any:
        device_id = _validate_identifier(device_id, "device_id")
        month = _validate_month(month)
        return await self._get(
            M_BEHAVIOR,
            {"deviceId": device_id, "month": month},
            self._headers,
        )

    async def get_riding(self, device_id: str, month: str) -> Any:
        device_id = _validate_identifier(device_id, "device_id")
        month = _validate_month(month)
        return await self._get(
            M_RIDING,
            {"deviceId": device_id, "month": month},
            self._headers,
        )

    async def get_function_config(self) -> Any:
        return await self._get(M_FUNCTION_CONFIG, {}, self._headers)


class VogeLegacyClient(_BaseReadOnlyClient):
    """Allowlisted legacy client for read-only account messages."""

    def __init__(
        self,
        session: ClientSession,
        token: str,
        credentials: LegacyApplicationCredentials,
        auth_failure_handler: AuthFailureHandler | None = None,
    ) -> None:
        super().__init__(session, token, auth_failure_handler)
        self._credentials = credentials

    def _headers(self) -> dict[str, str]:
        return build_legacy_headers(self._credentials, self._token)

    async def get_vehicle_messages(self, page_num: int, page_size: int) -> Any:
        if not 1 <= page_num <= 10_000:
            raise ReadOnlyViolation(L_MESSAGES.name, "invalid_page_num")
        if not 1 <= page_size <= 100:
            raise ReadOnlyViolation(L_MESSAGES.name, "invalid_page_size")
        return await self._get(
            L_MESSAGES,
            {"module": 1, "pageSize": page_size, "pageNum": page_num},
            self._headers,
        )

    async def get_message_info(self, message_id: str) -> Any:
        message_id = _validate_identifier(message_id, "message_id")
        return await self._get(L_MESSAGE_INFO, {"messageId": message_id}, self._headers)

    async def get_vehicles(self) -> Any:
        return await self._get(L_VEHICLES, {}, self._headers)
