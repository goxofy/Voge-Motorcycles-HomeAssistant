"""Shared VOGE entity classes."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VogeTelemetryCoordinator
from .runtime import VogeRuntimeData


def vehicle_device_info(runtime: VogeRuntimeData) -> DeviceInfo:
    """Return consistent metadata for the selected motorcycle."""
    telemetry = runtime.telemetry.data
    model_name = (
        telemetry.vehicle.display_name(runtime.product_name)
        if telemetry is not None
        else runtime.product_name
    )
    model_name = (model_name or "Motorcycle").strip() or "Motorcycle"
    folded = model_name.casefold()
    device_name = (
        model_name
        if folded.startswith("voge") or model_name.startswith("无极")
        else f"VOGE {model_name}"
    )
    return DeviceInfo(
        identifiers={(DOMAIN, runtime.device_key)},
        manufacturer="VOGE",
        model=model_name,
        name=device_name,
    )


class VogeTelemetryEntity(CoordinatorEntity[VogeTelemetryCoordinator]):
    """Base class for entities backed by modern telemetry."""

    _attr_has_entity_name = True

    def __init__(self, runtime: VogeRuntimeData, entity_key: str) -> None:
        super().__init__(runtime.telemetry)
        self.runtime = runtime
        self._attr_unique_id = f"{runtime.device_key}_{entity_key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the selected motorcycle device."""
        return vehicle_device_info(self.runtime)
