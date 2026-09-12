"""Read-only VOGE cloud integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.helpers import config_validation as cv

from .const import CONF_PRODUCT_ID, CONF_PRODUCT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: Any, config: dict[str, Any]) -> bool:
    """Set up the integration domain."""
    return True


def _entry_string(value: Any) -> str | None:
    """Return a non-empty config-entry scalar as text."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _sync_vehicle_metadata(
    hass: Any,
    entry: Any,
    runtime: Any,
    vehicle: Any,
) -> None:
    """Persist non-destructive modern vehicle metadata after an M1 refresh."""
    old_name = _entry_string(entry.data.get(CONF_PRODUCT_NAME))
    old_runtime_name = _entry_string(runtime.product_name)
    display_name = vehicle.display_name(old_name or old_runtime_name)
    entry_data = dict(entry.data)
    data_changed = False

    if old_name != display_name:
        entry_data[CONF_PRODUCT_NAME] = display_name
        data_changed = True
    runtime.product_name = display_name

    if vehicle.product_id is not None:
        runtime.product_id = vehicle.product_id
        if _entry_string(entry.data.get(CONF_PRODUCT_ID)) != vehicle.product_id:
            entry_data[CONF_PRODUCT_ID] = vehicle.product_id
            data_changed = True

    generated_titles = {"VOGE Motorcycle", "VOGE motorcycle"}
    if old_runtime_name is not None:
        generated_titles.add(old_runtime_name)
    if old_name is not None:
        generated_titles.add(old_name)
    title_changed = entry.title in generated_titles and entry.title != display_name

    if data_changed or title_changed:
        updates: dict[str, Any] = {}
        if data_changed:
            updates["data"] = entry_data
        if title_changed:
            updates["title"] = display_name
        hass.config_entries.async_update_entry(entry, **updates)


async def async_migrate_entry(hass: Any, entry: Any) -> bool:
    """Migrate pre-login entries to explicit token authentication mode."""
    from .const import AUTH_MODE_TOKEN, CONF_AUTH_MODE, CONF_MOBILE

    data = dict(entry.data)
    if CONF_AUTH_MODE not in data:
        data[CONF_AUTH_MODE] = AUTH_MODE_TOKEN if not data.get(CONF_MOBILE) else "password"
    hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True


async def async_setup_entry(hass: Any, entry: Any) -> bool:
    """Set up one VOGE account entry with automatic token recovery."""
    from homeassistant.exceptions import ConfigEntryAuthFailed
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .api import VogeAuthError, VogeLegacyClient, VogeModernClient
    from .auth import load_legacy_application_credentials
    from .auth_manager import VogeAuthManager
    from .const import (
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
        CONF_SCAN_INTERVAL,
        CONF_SERVER_TIMEZONE,
        CONF_STATS_INTERVAL,
        CONF_TOKEN,
        DEFAULT_ALERT_INTERVAL,
        DEFAULT_CONVERT_COORDINATES,
        DEFAULT_ENABLE_ALERTS,
        DEFAULT_SCAN_INTERVAL,
        DEFAULT_SERVER_TIMEZONE,
        DEFAULT_STATS_INTERVAL,
        PLATFORMS,
    )
    from .coordinator import (
        VogeAlertCoordinator,
        VogeStatisticsCoordinator,
        VogeTelemetryCoordinator,
    )
    from .runtime import VogeRuntimeData
    from .services import async_setup_services
    from .store import AlertDedupStore
    from .util import stable_hash

    device_id = entry.data[CONF_DEVICE_ID]
    stored_product_name = _entry_string(entry.data.get(CONF_PRODUCT_NAME))
    product_id = _entry_string(entry.data.get(CONF_PRODUCT_ID))
    product_name = stored_product_name or (
        f"VOGE product {product_id}" if product_id else "VOGE Motorcycle"
    )
    if product_name in {"VOGE Motorcycle", "VOGE motorcycle"} and product_id:
        product_name = f"VOGE product {product_id}"
    account_key = entry.data.get(CONF_ACCOUNT_KEY) or stable_hash(device_id)
    options = entry.options
    mode = entry.data.get(CONF_AUTH_MODE)
    if mode not in {AUTH_MODE_PASSWORD, AUTH_MODE_TOKEN}:
        mode = AUTH_MODE_PASSWORD if entry.data.get(CONF_MOBILE) else AUTH_MODE_TOKEN

    session = async_get_clientsession(hass)
    auth_manager = VogeAuthManager(
        hass,
        entry,
        session,
        mode=mode,
        token=entry.data.get(CONF_TOKEN),
        mobile=entry.data.get(CONF_MOBILE),
        password=entry.data.get(CONF_PASSWORD),
    )
    try:
        if not auth_manager.token:
            await auth_manager.async_authenticate(force=True)
    except VogeAuthError as err:
        auth_manager.close()
        raise ConfigEntryAuthFailed("VOGE authentication is required") from err

    modern_client = VogeModernClient(
        session,
        auth_manager.token,
        auth_manager.async_authenticate,
    )
    auth_manager.register_client(modern_client)
    telemetry = VogeTelemetryCoordinator(
        hass,
        entry,
        modern_client,
        device_id,
        interval_seconds=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        convert_coordinates=options.get(
            CONF_CONVERT_COORDINATES,
            DEFAULT_CONVERT_COORDINATES,
        ),
    )
    statistics = VogeStatisticsCoordinator(
        hass,
        entry,
        modern_client,
        device_id,
        interval_seconds=options.get(CONF_STATS_INTERVAL, DEFAULT_STATS_INTERVAL),
        server_timezone=options.get(CONF_SERVER_TIMEZONE, DEFAULT_SERVER_TIMEZONE),
    )

    legacy_client = None
    alerts = None
    if options.get(CONF_ENABLE_ALERTS, DEFAULT_ENABLE_ALERTS):
        credentials = load_legacy_application_credentials()
        if credentials is None:
            _LOGGER.warning(
                "VOGE vehicle-alert polling is disabled because local legacy application credentials are missing"
            )
        else:
            legacy_client = VogeLegacyClient(
                session,
                auth_manager.token,
                credentials,
                auth_manager.async_authenticate,
            )
            auth_manager.register_client(legacy_client)
            store = AlertDedupStore(hass, entry.entry_id)
            await store.async_load()
            alerts = VogeAlertCoordinator(
                hass,
                entry,
                legacy_client,
                store,
                interval_seconds=options.get(CONF_ALERT_INTERVAL, DEFAULT_ALERT_INTERVAL),
            )

    telemetry_entry = VogeRuntimeData(
        auth_manager=auth_manager,
        modern_client=modern_client,
        legacy_client=legacy_client,
        telemetry=telemetry,
        statistics=statistics,
        alerts=alerts,
        device_id=device_id,
        device_key=stable_hash(device_id),
        account_key=account_key,
        product_name=product_name,
        product_id=product_id,
        server_timezone=options.get(CONF_SERVER_TIMEZONE, DEFAULT_SERVER_TIMEZONE),
        convert_coordinates=options.get(
            CONF_CONVERT_COORDINATES,
            DEFAULT_CONVERT_COORDINATES,
        ),
        options_snapshot=dict(options),
    )
    entry.runtime_data = telemetry_entry
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_on_unload(auth_manager.close)

    try:
        await telemetry.async_config_entry_first_refresh()
        if telemetry.data is not None:
            _sync_vehicle_metadata(
                hass,
                entry,
                telemetry_entry,
                telemetry.data.vehicle,
            )
        await statistics.async_refresh()
        if alerts is not None:
            await alerts.async_refresh()
    except ConfigEntryAuthFailed:
        auth_manager.close()
        raise

    await async_setup_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: Any, entry: Any) -> None:
    """Reload only when options changed, not for metadata or token updates."""
    runtime = getattr(entry, "runtime_data", None)
    if runtime is None or dict(entry.options) != runtime.options_snapshot:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: Any, entry: Any) -> bool:
    """Unload all VOGE platforms and discard exact route caches."""
    from .const import PLATFORMS

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime = getattr(entry, "runtime_data", None)
        if runtime is not None:
            runtime.month_cache.clear()
            runtime.route_cache.clear()
    return unload_ok
