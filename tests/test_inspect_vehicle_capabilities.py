"""Privacy tests for the local VOGE capability inspection tool."""

import asyncio
import json
from typing import Any, cast

import pytest

from tools.inspect_vehicle_capabilities import (
    _field_types,
    _get,
    _response_status,
    _safe_menu,
    _safe_vehicle,
    _selection_index,
    _summarize_month_tracks,
)


def test_field_type_summary_filters_sensitive_and_untrusted_keys() -> None:
    assert _field_types(
        {
            "normalField": 1,
            "DEVICEID": "secret-device",
            "RouteId": "secret-route",
            "bad-key": "secret-in-key",
            "x" * 100: "secret-long-key",
        }
    ) == {"normalField": "int"}


def test_menu_summary_accepts_only_binary_capability_values() -> None:
    assert _safe_menu(
        {
            "supported": 1,
            "unsupported": "0",
            "boolean": True,
            "floatFlag": 1.0,
            "arbitrary": "identifier-secret",
            "nested": {"token": "secret"},
            "TOKEN": 1,
            "bad-key": 1,
        }
    ) == {
        "boolean": True,
        "floatFlag": 1,
        "supported": 1,
        "unsupported": 0,
    }


def test_vehicle_summary_never_copies_nested_or_unbounded_values() -> None:
    summary = _safe_vehicle(
        {
            "deviceId": "secret-device",
            "vin": "secret-vin",
            "deviceName": "CU250 II代自动挡",
            "productName": {"token": "nested-secret"},
            "productId": {"deviceId": "nested-device-secret"},
            "menu": {"safeCapability": 1, "unsafeCapability": "secret-menu"},
        },
        2,
    )
    serialized = json.dumps(summary, ensure_ascii=False)

    assert summary["ordinal"] == 2
    assert summary["model_label_candidates"] == {
        "deviceName": "CU250 II代自动挡"
    }
    assert summary["product_id"] is None
    assert summary["device_id_present"] is True
    assert summary["vin_present"] is True
    assert summary["menu"] == {"safeCapability": 1}
    for secret in (
        "secret-device",
        "secret-vin",
        "nested-secret",
        "nested-device-secret",
        "secret-menu",
    ):
        assert secret not in serialized


def test_response_status_only_emits_expected_scalar_types() -> None:
    assert _response_status(
        {"code": {"token": "secret"}, "success": "true"},
        200,
    ) == {"http_status": 200, "code": None, "success": None}
    assert _response_status({"code": "200", "success": True}, 200) == {
        "http_status": 200,
        "code": 200,
        "success": True,
    }


def test_month_track_summary_keeps_route_id_private() -> None:
    summary = _summarize_month_tracks(
        [{"list": [{"routeId": "private-route-id", "distance": 10}]}]
    )
    assert summary.pop("_first_route_id") == "private-route-id"
    assert "private-route-id" not in json.dumps(summary)
    assert summary["route_id_found_locally"] is True


def test_vehicle_selection_requires_explicit_valid_ordinal_for_multiple() -> None:
    assert _selection_index("", 1) == 0
    assert _selection_index("", 2) is None
    assert _selection_index("2", 2) == 1
    assert _selection_index("0", 2) is None
    assert _selection_index("3", 2) is None
    assert _selection_index("not-a-number", 2) is None


def test_inspector_rejects_arbitrary_endpoint_and_wrong_query_shape() -> None:
    with pytest.raises(RuntimeError, match="endpoint_not_allowed"):
        asyncio.run(_get(cast(Any, object()), "/arbitrary", {}, {}))

    with pytest.raises(RuntimeError, match="endpoint_not_allowed"):
        asyncio.run(
            _get(
                cast(Any, object()),
                "/api/app/favorite/index",
                {},
                {},
            )
        )

    with pytest.raises(RuntimeError, match="endpoint_not_allowed"):
        asyncio.run(
            _get(
                cast(Any, object()),
                "/api/app/favorite/device",
                {},
                {"deviceId": "unexpected"},
            )
        )
