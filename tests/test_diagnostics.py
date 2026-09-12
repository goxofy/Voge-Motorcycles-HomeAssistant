"""Privacy regression tests for VOGE diagnostics."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.voge.diagnostics import async_get_config_entry_diagnostics
from custom_components.voge.models import parse_diagnosis, parse_vehicle


@pytest.mark.asyncio
async def test_diagnostics_excludes_recursive_sensitive_values() -> None:
    """Diagnostics expose capability state but never raw credentials or identifiers."""
    vehicle = parse_vehicle(
        {
            "deviceId": "raw-device-id-secret",
            "deviceName": "CU250 II代自动挡",
            "productName": "Synthetic CU250",
            "vin": "LONCINVINSECRET123",
            "userId": "raw-user-id-secret",
            "deviceIdIot": "raw-iot-id-secret",
            "amapDeviceId": "raw-amap-id-secret",
            "geoLatitude": "29.56",
            "geoLongitude": "106.55",
            "formattedAddress": "secret address",
            "menu": {"sumDistance": 1, "frontTireP": 1},
        }
    )
    diagnosis = parse_diagnosis(
        {
            "deviceId": "raw-device-id-secret",
            "voltage": "12.6",
            "menu": {"voltage": 1},
            "canList": [
                {
                    "vin": "LONCINVINSECRET123",
                    "message": "route-point-secret",
                }
            ],
        }
    )
    assert vehicle is not None
    assert diagnosis is not None

    runtime = SimpleNamespace(
        auth_manager=SimpleNamespace(
            mode="password",
            token="access-token-secret",
            has_password=True,
        ),
        device_id="raw-device-id-secret",
        device_key="device-key-secret",
        account_key="account-key-secret",
        product_name="Synthetic CU250",
        product_id="synthetic-product-secret",
        server_timezone="Asia/Shanghai",
        convert_coordinates=True,
        telemetry=SimpleNamespace(
            data=SimpleNamespace(
                vehicle=vehicle,
                diagnosis=diagnosis,
                coordinates_wgs84=(29.55, 106.54),
                bound_vehicle_count=1,
                diagnosis_status="matched",
            ),
            last_update_success=True,
            last_exception=None,
        ),
        statistics=SimpleNamespace(
            data=SimpleNamespace(month="2026-09", summary=None),
            last_update_success=True,
            last_exception=None,
        ),
        alerts=None,
        month_cache={"2026-09": object()},
        route_cache={"route-secret": object()},
    )
    entry = SimpleNamespace(title="Synthetic CU250", runtime_data=runtime)

    result = await async_get_config_entry_diagnostics(None, entry)  # type: ignore[arg-type]
    serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)

    for secret in (
        "access-token-secret",
        "13800000000",
        "synthetic-secret",
        "8e1843033a0f6ee52e2f618aa8ebbef4",
        "refresh-secret",
        "LONCINVINSECRET123",
        "raw-device-id-secret",
        "raw-user-id-secret",
        "raw-iot-id-secret",
        "raw-amap-id-secret",
        "synthetic-product-secret",
        "secret address",
        "route-point-secret",
        "message-body-secret",
        "message-param-secret",
        "message-id-secret",
        "29.56",
        "106.55",
    ):
        assert secret not in serialized

    assert result["auth"] == {
        "mode": "password",
        "token_configured": True,
        "mobile_configured": True,
        "password_configured": True,
    }
    assert result["entry"]["product_id_configured"] is True
    assert result["entry"]["catalog_match"] == {
        "source": "booking_model_catalog",
        "observed_on": "2026-09-12",
        "series": "CU",
        "tline_code": "906",
        "model_name": "CU250Ⅱ代",
        "model_code": "997",
    }
    assert result["telemetry"]["location_available"] is True
    assert result["telemetry"]["exact_coordinates_included"] is False
    assert result["telemetry"]["vin_included"] is False
    assert result["route_cache"]["coordinates_included"] is False
