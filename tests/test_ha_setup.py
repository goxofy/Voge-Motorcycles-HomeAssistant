"""Full Home Assistant setup smoke tests with every cloud call mocked."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import (  # type: ignore[reportMissingImports]
    MockConfigEntry,
)

from custom_components.voge import _async_update_listener, _sync_vehicle_metadata
from custom_components.voge.const import (
    AUTH_MODE_PASSWORD,
    AUTH_MODE_TOKEN,
    CONF_ACCOUNT_KEY,
    CONF_ALERT_INTERVAL,
    CONF_AUTH_MODE,
    CONF_CONVERT_COORDINATES,
    CONF_DEVICE_ID,
    CONF_ENABLE_ALERTS,
    CONF_MOBILE,
    CONF_PASSWORD,
    CONF_PRODUCT_ID,
    CONF_PRODUCT_NAME,
    CONF_SCAN_INTERVAL,
    CONF_SERVER_TIMEZONE,
    CONF_STATS_INTERVAL,
    CONF_TOKEN,
    DOMAIN,
)
from custom_components.voge.models import parse_vehicle

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.mark.asyncio
async def test_config_flow_creates_token_only_entry(hass, enable_custom_integrations) -> None:
    """The user flow stores an existing token and never asks for a password."""
    vehicle = parse_vehicle(
        {
            "deviceId": "synthetic-device",
            "deviceName": "CU250 II代自动挡",
            "productName": "CU250Ⅱ代",
            "productId": "2",
            "userId": "synthetic-account",
            "menu": {"sumDistance": 1},
        }
    )
    assert vehicle is not None
    with (
        patch(
            "custom_components.voge.config_flow._validate_token",
            new=AsyncMock(return_value=[vehicle]),
        ),
        patch(
            "custom_components.voge.async_setup_entry",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_TOKEN: "synthetic-token"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEVICE_ID] == "synthetic-device"
    assert result["title"] == "CU250 II代自动挡"
    assert result["data"][CONF_TOKEN] == "synthetic-token"
    assert result["data"][CONF_AUTH_MODE] == AUTH_MODE_TOKEN
    assert result["data"][CONF_PRODUCT_ID] == "2"
    assert "model_code" not in result["data"]
    assert "model_series" not in result["data"]
    assert "password" not in result["data"]


@pytest.mark.asyncio
async def test_config_flow_logs_in_with_password_and_stores_local_credentials(
    hass,
    enable_custom_integrations,
) -> None:
    """The default flow validates password credentials without contacting production."""
    vehicle = parse_vehicle(
        {
            "deviceId": "synthetic-device",
            "productName": "Synthetic CU250",
            "userId": "synthetic-account",
            "menu": {"sumDistance": 1},
        }
    )
    assert vehicle is not None
    validate_credentials = AsyncMock(return_value=("synthetic-token", [vehicle]))
    with patch(
        "custom_components.voge.config_flow._validate_credentials",
        new=validate_credentials,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_AUTH_MODE: AUTH_MODE_PASSWORD},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "credentials"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_MOBILE: " 13800000000 ",
                CONF_PASSWORD: "synthetic-secret",
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Synthetic CU250"
    assert result["data"][CONF_AUTH_MODE] == AUTH_MODE_PASSWORD
    assert result["data"][CONF_TOKEN] == "synthetic-token"
    assert result["data"][CONF_MOBILE] == "13800000000"
    assert result["data"][CONF_PASSWORD] == "synthetic-secret"
    assert CONF_PRODUCT_ID not in result["data"]
    assert "synthetic-secret" not in result["title"]
    validate_credentials.assert_awaited_once_with(
        hass,
        "13800000000",
        "synthetic-secret",
    )


@pytest.mark.asyncio
async def test_password_reauth_preserves_selected_vehicle(hass, enable_custom_integrations) -> None:
    """Password reauthentication updates credentials without changing device selection."""
    vehicle = parse_vehicle(
        {
            "deviceId": "synthetic-device",
            "productName": "Synthetic CU250",
            "userId": "synthetic-account",
            "menu": {"sumDistance": 1},
        }
    )
    assert vehicle is not None
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Synthetic CU250",
        data={
            CONF_AUTH_MODE: AUTH_MODE_PASSWORD,
            CONF_TOKEN: "expired-token",
            CONF_MOBILE: "13800000000",
            CONF_PASSWORD: "old-secret",
            CONF_DEVICE_ID: "synthetic-device",
            CONF_PRODUCT_NAME: "Synthetic CU250",
            CONF_PRODUCT_ID: "synthetic-product",
            CONF_ACCOUNT_KEY: "account-key",
        },
    )
    entry.add_to_hass(hass)
    validate_credentials = AsyncMock(return_value=("replacement-token", [vehicle]))
    with (
        patch(
            "custom_components.voge.config_flow._validate_credentials",
            new=validate_credentials,
        ),
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data={},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_MOBILE: " 13900000000 ",
                CONF_PASSWORD: "replacement-secret",
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_AUTH_MODE] == AUTH_MODE_PASSWORD
    assert entry.data[CONF_DEVICE_ID] == "synthetic-device"
    assert entry.data[CONF_TOKEN] == "replacement-token"
    assert entry.data[CONF_MOBILE] == "13900000000"
    assert entry.data[CONF_PASSWORD] == "replacement-secret"
    validate_credentials.assert_awaited_once_with(
        hass,
        "13900000000",
        "replacement-secret",
    )


@pytest.mark.asyncio
async def test_options_flow_uses_framework_config_entry(hass, enable_custom_integrations) -> None:
    """HA 2026.9 injects the config entry into OptionsFlow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Synthetic CU250",
        data={
            CONF_TOKEN: "synthetic-token",
            CONF_DEVICE_ID: "synthetic-device",
            CONF_PRODUCT_NAME: "Synthetic CU250",
            CONF_PRODUCT_ID: "synthetic-product",
            CONF_ACCOUNT_KEY: "account-key",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_SCAN_INTERVAL: 90,
            CONF_STATS_INTERVAL: 1800,
            CONF_ALERT_INTERVAL: 45,
            CONF_SERVER_TIMEZONE: "Asia/Shanghai",
            CONF_CONVERT_COORDINATES: True,
            CONF_ENABLE_ALERTS: False,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.asyncio
async def test_entry_setup_creates_entities_without_network(
    hass,
    enable_custom_integrations,
) -> None:
    """A fully mocked config entry loads platforms and unloads cleanly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Synthetic CU250",
        data={
            CONF_TOKEN: "synthetic-token",
            CONF_DEVICE_ID: "synthetic-device",
            CONF_PRODUCT_NAME: "Synthetic CU250",
            CONF_ACCOUNT_KEY: "account-key",
        },
        options={
            CONF_SCAN_INTERVAL: 90,
            CONF_STATS_INTERVAL: 1800,
            CONF_SERVER_TIMEZONE: "Asia/Shanghai",
            CONF_CONVERT_COORDINATES: True,
            CONF_ENABLE_ALERTS: False,
        },
        unique_id="account_account-key",
    )
    entry.add_to_hass(hass)
    reload_entry = AsyncMock()
    with (
        patch.object(hass.config_entries, "async_reload", new=reload_entry),
        patch(
            "custom_components.voge.api.VogeModernClient.get_devices",
            new=AsyncMock(
                return_value=[
                    {
                        "deviceId": "synthetic-device",
                        "productId": "synthetic-product",
                        "productName": "Synthetic CU250",
                        "geoLatitude": "29.56",
                        "geoLongitude": "106.55",
                        "restFuelLevel": "8.0",
                        "restTrip": "220",
                        "sumDistance": "1234",
                        "distanceMo": "88",
                        "menu": {
                            "restFuelLevel": 1,
                            "restTrip": 1,
                            "sumDistance": 1,
                            "voltage": 1,
                        },
                    }
                ]
            ),
        ),
        patch(
            "custom_components.voge.api.VogeModernClient.get_diagnosis",
            new=AsyncMock(
                return_value={
                    "deviceId": "synthetic-device",
                    "voltage": "12.6",
                    "timeGen": "2026-09-11 12:00:00",
                }
            ),
        ),
        patch(
            "custom_components.voge.api.VogeModernClient.get_month_index",
            new=AsyncMock(
                return_value={
                    "deviceId": "synthetic-device",
                    "distance": "88",
                }
            ),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    states = list(hass.states.async_all())
    assert any(state.entity_id.startswith("device_tracker.") for state in states)
    assert any(
        state.entity_id.startswith("sensor.") and state.state == "12.6"
        for state in states
    )
    assert entry.data[CONF_PRODUCT_ID] == "synthetic-product"
    reload_entry.assert_not_awaited()
    assert not any(state.entity_id.startswith("event.") for state in states)
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.asyncio
async def test_supported_empty_field_is_unknown_but_unsupported_field_is_unavailable(
    hass,
    enable_custom_integrations,
) -> None:
    """A declared capability may be temporarily empty without becoming unavailable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Synthetic VOGE model",
        data={
            CONF_TOKEN: "synthetic-token",
            CONF_DEVICE_ID: "synthetic-device",
            CONF_PRODUCT_NAME: "Synthetic VOGE model",
            CONF_PRODUCT_ID: "synthetic-product",
            CONF_ACCOUNT_KEY: "account-key-2",
        },
        options={
            CONF_SCAN_INTERVAL: 90,
            CONF_STATS_INTERVAL: 1800,
            CONF_SERVER_TIMEZONE: "Asia/Shanghai",
            CONF_CONVERT_COORDINATES: True,
            CONF_ENABLE_ALERTS: False,
        },
        unique_id="account_account-key-2",
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.voge.api.VogeModernClient.get_devices",
            new=AsyncMock(
                return_value=[
                    {
                        "deviceId": "synthetic-device",
                        "productId": "synthetic-product",
                        "productName": "Synthetic VOGE model",
                        "menu": {"voltage": 1, "frontTireP": 0},
                    }
                ]
            ),
        ),
        patch(
            "custom_components.voge.api.VogeModernClient.get_diagnosis",
            new=AsyncMock(return_value={"deviceId": "synthetic-device"}),
        ),
        patch(
            "custom_components.voge.api.VogeModernClient.get_month_index",
            new=AsyncMock(return_value={"deviceId": "synthetic-device"}),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    voltage = hass.states.get("sensor.voge_synthetic_voge_model_voltage")
    front_tire_pressure = hass.states.get(
        "sensor.voge_synthetic_voge_model_front_tire_pressure"
    )
    assert voltage is not None
    assert front_tire_pressure is not None
    assert voltage.state == "unknown"
    assert front_tire_pressure.state == "unavailable"
    assert await hass.config_entries.async_unload(entry.entry_id)


def test_metadata_sync_preserves_missing_product_id_and_custom_title() -> None:
    """Transient M1 omissions do not erase useful local metadata."""
    vehicle = parse_vehicle(
        {
            "deviceId": "synthetic-device",
            "deviceName": "CU250 II代自动挡",
        }
    )
    assert vehicle is not None
    update_entry = Mock()
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_update_entry=update_entry)
    )
    entry = SimpleNamespace(
        data={
            CONF_PRODUCT_NAME: "CU250Ⅱ代",
            CONF_PRODUCT_ID: "opaque-modern-product",
            "model_code": "legacy-experimental-value",
        },
        title="My Motorcycle",
    )
    runtime = SimpleNamespace(
        product_name="CU250Ⅱ代",
        product_id="opaque-modern-product",
    )

    _sync_vehicle_metadata(hass, entry, runtime, vehicle)

    update_entry.assert_called_once()
    updates = update_entry.call_args.kwargs
    assert updates["data"][CONF_PRODUCT_NAME] == "CU250 II代自动挡"
    assert updates["data"][CONF_PRODUCT_ID] == "opaque-modern-product"
    assert updates["data"]["model_code"] == "legacy-experimental-value"
    assert "title" not in updates
    assert runtime.product_name == "CU250 II代自动挡"
    assert runtime.product_id == "opaque-modern-product"


def test_metadata_sync_updates_only_an_automatically_generated_title() -> None:
    """A more precise deviceName replaces the old generated family title."""
    vehicle = parse_vehicle(
        {
            "deviceId": "synthetic-device",
            "deviceName": "CU250 II代自动挡",
            "productName": "CU250Ⅱ代",
            "productId": "2",
        }
    )
    assert vehicle is not None
    update_entry = Mock()
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_update_entry=update_entry)
    )
    entry = SimpleNamespace(
        data={CONF_PRODUCT_NAME: "CU250Ⅱ代"},
        title="CU250Ⅱ代",
    )
    runtime = SimpleNamespace(product_name="CU250Ⅱ代", product_id=None)

    _sync_vehicle_metadata(hass, entry, runtime, vehicle)

    updates = update_entry.call_args.kwargs
    assert updates["title"] == "CU250 II代自动挡"
    assert updates["data"][CONF_PRODUCT_ID] == "2"
    assert runtime.product_id == "2"


def test_metadata_sync_updates_generated_product_id_title() -> None:
    """A product-ID fallback title is generated metadata, not a custom title."""
    vehicle = parse_vehicle(
        {
            "deviceId": "synthetic-device",
            "deviceName": "CU250 II代自动挡",
            "productId": "2",
        }
    )
    assert vehicle is not None
    update_entry = Mock()
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_update_entry=update_entry)
    )
    entry = SimpleNamespace(data={CONF_PRODUCT_ID: "2"}, title="VOGE product 2")
    runtime = SimpleNamespace(product_name="VOGE product 2", product_id="2")

    _sync_vehicle_metadata(hass, entry, runtime, vehicle)

    updates = update_entry.call_args.kwargs
    assert updates["title"] == "CU250 II代自动挡"
    assert updates["data"][CONF_PRODUCT_NAME] == "CU250 II代自动挡"


@pytest.mark.asyncio
async def test_update_listener_ignores_token_and_metadata_updates() -> None:
    """ConfigEntry data persistence must not interrupt live coordinators."""
    reload_entry = AsyncMock()
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_reload=reload_entry)
    )
    entry = SimpleNamespace(
        entry_id="entry-id",
        data={CONF_TOKEN: "rotated-token"},
        options={CONF_SCAN_INTERVAL: 90},
        runtime_data=SimpleNamespace(
            options_snapshot={CONF_SCAN_INTERVAL: 90}
        ),
    )

    await _async_update_listener(hass, entry)

    reload_entry.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_listener_reloads_when_options_change() -> None:
    """Polling and coordinate options continue to take effect through reload."""
    reload_entry = AsyncMock()
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_reload=reload_entry)
    )
    entry = SimpleNamespace(
        entry_id="entry-id",
        options={CONF_SCAN_INTERVAL: 120},
        runtime_data=SimpleNamespace(
            options_snapshot={CONF_SCAN_INTERVAL: 90}
        ),
    )

    await _async_update_listener(hass, entry)

    reload_entry.assert_awaited_once_with("entry-id")


def test_vehicle_label_uses_product_id_when_product_name_is_missing() -> None:
    """A product ID remains visible when the service omits productName."""
    from custom_components.voge.config_flow import _vehicle_label

    vehicle = parse_vehicle({"deviceId": "synthetic-device", "productId": "2"})
    assert vehicle is not None
    assert _vehicle_label(vehicle, 1) == "VOGE product 2 #1"


def test_vehicle_label_prefers_precise_device_name() -> None:
    """The bound vehicle name preserves variants that productName may omit."""
    from custom_components.voge.config_flow import _vehicle_label

    vehicle = parse_vehicle(
        {
            "deviceId": "synthetic-device",
            "deviceName": "CU250 II代自动挡",
            "productName": "CU250Ⅱ代",
            "productId": "2",
        }
    )
    assert vehicle is not None
    assert _vehicle_label(vehicle, 1) == "CU250 II代自动挡 #1"
