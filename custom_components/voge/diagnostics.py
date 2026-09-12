"""Privacy-preserving diagnostics for VOGE."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import VERSION
from .model_catalog import CATALOG_OBSERVED_ON, CATALOG_SOURCE
from .runtime import VogeRuntimeData
from .util import redact_identifier


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics without credentials, coordinates, routes, IDs, or messages."""
    runtime: VogeRuntimeData = entry.runtime_data
    telemetry = runtime.telemetry.data
    statistics = runtime.statistics.data
    alerts = runtime.alerts.data if runtime.alerts is not None else None
    catalog_model = telemetry.vehicle.catalog_model() if telemetry is not None else None

    result: dict[str, Any] = {
        "integration_version": VERSION,
        "entry": {
            "title": entry.title,
            "device_id": redact_identifier(runtime.device_id),
            "device_key": runtime.device_key,
            "account_key": runtime.account_key,
            "product_name": runtime.product_name,
            "product_id_configured": bool(runtime.product_id),
            "catalog_match": (
                {
                    "source": CATALOG_SOURCE,
                    "observed_on": CATALOG_OBSERVED_ON,
                    "series": catalog_model.series,
                    "tline_code": catalog_model.tline_code,
                    "model_name": catalog_model.model_name,
                    "model_code": catalog_model.model_code,
                }
                if catalog_model is not None
                else None
            ),
            "server_timezone": runtime.server_timezone,
            "convert_coordinates": runtime.convert_coordinates,
            "legacy_alerts_configured": runtime.alerts is not None,
        },
        "auth": {
            "mode": runtime.auth_manager.mode,
            "token_configured": bool(runtime.auth_manager.token),
            "mobile_configured": runtime.auth_manager.has_password,
            "password_configured": runtime.auth_manager.has_password,
        },
        "coordinators": {
            "telemetry": {
                "last_update_success": runtime.telemetry.last_update_success,
                "last_exception_type": (
                    type(runtime.telemetry.last_exception).__name__
                    if runtime.telemetry.last_exception is not None
                    else None
                ),
            },
            "statistics": {
                "last_update_success": runtime.statistics.last_update_success,
                "last_exception_type": (
                    type(runtime.statistics.last_exception).__name__
                    if runtime.statistics.last_exception is not None
                    else None
                ),
            },
            "alerts": None,
        },
        "telemetry": None,
        "statistics": None,
        "alerts": None,
        "route_cache": {
            "months": len(runtime.month_cache),
            "routes": len(runtime.route_cache),
            "coordinates_included": False,
        },
    }

    if telemetry is not None:
        result["telemetry"] = {
            "bound_vehicle_count": telemetry.bound_vehicle_count,
            "diagnosis_status": telemetry.diagnosis_status,
            "location_available": telemetry.coordinates_wgs84 is not None,
            "menu": dict(sorted(telemetry.vehicle.menu.items())),
            "available_fields": {
                "rest_fuel_liters": telemetry.vehicle.rest_fuel_liters is not None,
                "remaining_range_km": telemetry.vehicle.remaining_range_km is not None,
                "consumption_per_100km": telemetry.vehicle.consumption_per_100km is not None,
                "total_mileage_km": telemetry.vehicle.total_mileage_km is not None,
                "monthly_mileage_km": telemetry.vehicle.monthly_mileage_km is not None,
                "diagnosis": telemetry.diagnosis is not None,
                "can_list": bool(telemetry.diagnosis and telemetry.diagnosis.can_list),
            },
            "diagnosis_menu": (
                dict(sorted(telemetry.diagnosis.menu.items()))
                if telemetry.diagnosis is not None
                else {}
            ),
            "can_group_count": (
                len(telemetry.diagnosis.can_list) if telemetry.diagnosis is not None else 0
            ),
            "exact_coordinates_included": False,
            "address_included": False,
            "vin_included": False,
        }

    if statistics is not None:
        result["statistics"] = {
            "month": statistics.month,
            "summary_available": statistics.summary is not None,
            "coordinates_included": False,
        }

    if runtime.alerts is not None:
        result["coordinators"]["alerts"] = {
            "last_update_success": runtime.alerts.last_update_success,
            "last_exception_type": (
                type(runtime.alerts.last_exception).__name__
                if runtime.alerts.last_exception is not None
                else None
            ),
        }
        if alerts is not None:
            result["alerts"] = {
                "new_message_count_last_poll": len(alerts.messages),
                "page_scan_truncated": alerts.page_scan_truncated,
                "server_pages": alerts.server_pages,
                "server_total": alerts.server_total,
                "message_content_included": False,
                "message_ids_included": False,
                "message_params_included": False,
            }

    return result
