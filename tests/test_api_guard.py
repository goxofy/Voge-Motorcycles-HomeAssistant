"""Tests that the client exposes only exact read-only endpoint shapes."""

import pytest

from custom_components.voge.api import (
    M_DEVICES,
    M_MONTH_TRACKS,
    Endpoint,
    ReadOnlyViolation,
    _validate_request,
)


def test_allowlisted_request_shape_is_accepted() -> None:
    _validate_request(M_DEVICES, {})
    _validate_request(M_MONTH_TRACKS, {"deviceId": "x", "month": "2026-09"})


def test_extra_or_missing_query_keys_are_rejected() -> None:
    with pytest.raises(ReadOnlyViolation, match="query_keys_not_allowlisted"):
        _validate_request(M_DEVICES, {"deviceId": "x"})
    with pytest.raises(ReadOnlyViolation, match="query_keys_not_allowlisted"):
        _validate_request(M_MONTH_TRACKS, {"deviceId": "x"})


def test_unlisted_get_path_is_rejected_even_if_host_is_known() -> None:
    mutating_get = Endpoint(
        "forbidden.message_read",
        "https://voge.loncinindustries.com/api",
        "/voge-system/app/message/upReadStatus",
        frozenset({"module"}),
        False,
        1024,
    )
    with pytest.raises(ReadOnlyViolation, match="endpoint_not_allowlisted"):
        _validate_request(mutating_get, {"module": 1})


@pytest.mark.parametrize(
    "forbidden_path",
    (
        "/api/login/sendSms",
        "/api/login/sendVoiceCode",
        "/api/login/loginSync",
        "/jpush/register",
        "/gateway.do",
        "/api/app/vehicle/unlock",
        "/api/app/vehicle/arm",
    ),
)
def test_auth_messaging_store_and_control_paths_are_not_allowlisted(
    forbidden_path: str,
) -> None:
    """The read-only transport rejects every non-data operation path."""
    endpoint = Endpoint(
        "forbidden.operation",
        "https://iot-api.loncinindustries.com",
        forbidden_path,
        frozenset(),
        True,
        1024,
    )
    with pytest.raises(ReadOnlyViolation, match="endpoint_not_allowlisted"):
        _validate_request(endpoint, {})


def test_non_tls_endpoint_is_rejected() -> None:
    endpoint = Endpoint(
        "unknown",
        "http://iot-api.loncinindustries.com",
        "/api/app/favorite/device",
        frozenset(),
        True,
        1024,
    )
    with pytest.raises(ReadOnlyViolation, match="endpoint_not_allowlisted"):
        _validate_request(endpoint, {})
