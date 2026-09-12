"""Response-enabled read-only trip and route actions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .api import VogeApiError, VogeAuthError
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DAY,
    ATTR_MONTH,
    ATTR_ROUTE_ID,
    DOMAIN,
    SERVICE_GET_DAY_GEOJSON,
    SERVICE_GET_MONTH_TRIPS,
    SERVICE_GET_ROUTE_GEOJSON,
)
from .routes import (
    DayTripSummary,
    RouteDetail,
    RouteParseError,
    day_routes_to_geojson,
    month_tracks_to_dict,
    parse_month_tracks,
    parse_route_detail,
    route_ids_for_day,
    route_ids_for_month,
    route_to_geojson,
)
from .runtime import VogeRuntimeData

_MONTH = vol.Match(r"^\d{4}-(0[1-9]|1[0-2])$")

MONTH_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_MONTH): vol.All(cv.string, _MONTH),
    }
)
ROUTE_SCHEMA = MONTH_SCHEMA.extend(
    {
        vol.Required(ATTR_ROUTE_ID): cv.string,
    }
)
DAY_SCHEMA = MONTH_SCHEMA.extend(
    {
        vol.Required(ATTR_DAY): cv.string,
    }
)

_MONTH_CACHE_TTL = timedelta(minutes=5)
_ROUTE_CACHE_TTL = timedelta(minutes=10)


def _runtime_for_call(hass: HomeAssistant, call: ServiceCall) -> tuple[ConfigEntry, VogeRuntimeData]:
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise HomeAssistantError("The selected VOGE config entry does not exist")
    runtime = getattr(entry, "runtime_data", None)
    if not isinstance(runtime, VogeRuntimeData):
        raise HomeAssistantError("The selected VOGE config entry is not loaded")
    return entry, runtime


def _handle_auth_failure(entry: ConfigEntry, hass: HomeAssistant) -> None:
    """Start config-entry reauthentication without awaiting the synchronous scheduler."""
    entry.async_start_reauth(hass)


async def _get_month_groups(
    runtime: VogeRuntimeData,
    month: str,
) -> list[DayTripSummary]:
    cached = runtime.month_cache.get(month)
    now = datetime.now(UTC)
    if cached is not None and now - cached[0] <= _MONTH_CACHE_TTL:
        return cached[1]

    raw = await runtime.modern_client.get_month_tracks(runtime.device_id, month)
    groups = parse_month_tracks(raw)
    runtime.month_cache[month] = (now, groups)
    return groups


async def _get_route(
    runtime: VogeRuntimeData,
    route_id: str,
) -> RouteDetail:
    cached = runtime.route_cache.get(route_id)
    now = datetime.now(UTC)
    if cached is not None and now - cached[0] <= _ROUTE_CACHE_TTL:
        return cached[1]

    raw = await runtime.modern_client.get_route_detail(route_id)
    route = parse_route_detail(raw, route_id)
    runtime.route_cache[route_id] = (now, route)
    return route


async def _month_trips(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    entry, runtime = _runtime_for_call(hass, call)
    month = call.data[ATTR_MONTH]
    try:
        async with runtime.route_lock:
            groups = await _get_month_groups(runtime, month)
    except VogeAuthError as err:
        _handle_auth_failure(entry, hass)
        raise HomeAssistantError("VOGE authentication failed; reauthentication is required") from err
    except VogeApiError as err:
        raise HomeAssistantError(str(err)) from err

    response = month_tracks_to_dict(groups)
    response["month"] = month
    response["day_count"] = len(groups)
    response["route_count"] = sum(len(group.trips) for group in groups)
    return response


async def _route_geojson(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    entry, runtime = _runtime_for_call(hass, call)
    month = call.data[ATTR_MONTH]
    route_id = call.data[ATTR_ROUTE_ID]
    try:
        async with runtime.route_lock:
            groups = await _get_month_groups(runtime, month)
            if route_id not in route_ids_for_month(groups):
                raise HomeAssistantError(
                    "The route ID was not returned for the configured vehicle and month"
                )
            route = await _get_route(runtime, route_id)
    except VogeAuthError as err:
        _handle_auth_failure(entry, hass)
        raise HomeAssistantError("VOGE authentication failed; reauthentication is required") from err
    except (VogeApiError, RouteParseError) as err:
        raise HomeAssistantError(str(err)) from err

    return route_to_geojson(route, runtime.convert_coordinates)


async def _day_geojson(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    entry, runtime = _runtime_for_call(hass, call)
    month = call.data[ATTR_MONTH]
    day = call.data[ATTR_DAY]
    routes: list[RouteDetail] = []
    error_count = 0

    try:
        async with runtime.route_lock:
            groups = await _get_month_groups(runtime, month)
            route_ids = route_ids_for_day(groups, day)
            if not route_ids:
                raise HomeAssistantError(
                    "The day was not returned for the configured vehicle and month"
                )
            for route_id in route_ids:
                try:
                    routes.append(await _get_route(runtime, route_id))
                except VogeAuthError:
                    raise
                except (VogeApiError, RouteParseError):
                    error_count += 1
    except VogeAuthError as err:
        _handle_auth_failure(entry, hass)
        raise HomeAssistantError("VOGE authentication failed; reauthentication is required") from err
    except VogeApiError as err:
        raise HomeAssistantError(str(err)) from err

    return day_routes_to_geojson(
        day,
        routes,
        runtime.convert_coordinates,
        partial=error_count > 0,
        error_count=error_count,
    )


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register strict read-only response actions once."""

    async def month_trips(call: ServiceCall) -> dict[str, Any]:
        return await _month_trips(hass, call)

    async def route_geojson(call: ServiceCall) -> dict[str, Any]:
        return await _route_geojson(hass, call)

    async def day_geojson(call: ServiceCall) -> dict[str, Any]:
        return await _day_geojson(hass, call)

    if not hass.services.has_service(DOMAIN, SERVICE_GET_MONTH_TRIPS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_MONTH_TRIPS,
            month_trips,
            schema=MONTH_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_GET_ROUTE_GEOJSON):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_ROUTE_GEOJSON,
            route_geojson,
            schema=ROUTE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_GET_DAY_GEOJSON):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_DAY_GEOJSON,
            day_geojson,
            schema=DAY_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
