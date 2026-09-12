"""GPS device tracker for a VOGE motorcycle."""

from __future__ import annotations

from homeassistant.components.device_tracker.const import SourceType
from homeassistant.components.device_tracker.entity import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import VogeTelemetryEntity
from .runtime import VogeRuntimeData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the selected motorcycle tracker."""
    runtime: VogeRuntimeData = entry.runtime_data
    async_add_entities([VogeDeviceTracker(runtime)])


class VogeDeviceTracker(VogeTelemetryEntity, TrackerEntity):
    """The last cloud-reported motorcycle location."""

    _attr_translation_key = "motorcycle_location"
    _attr_source_type = SourceType.GPS

    def __init__(self, runtime: VogeRuntimeData) -> None:
        super().__init__(runtime, "location")

    @property
    def available(self) -> bool:
        """Keep the last valid location unless the coordinator has never succeeded."""
        return (
            self.coordinator.data is not None
            and self.coordinator.data.coordinates_wgs84 is not None
        )

    @property
    def latitude(self) -> float | None:
        """Return WGS84 latitude."""
        if self.coordinator.data is None or self.coordinator.data.coordinates_wgs84 is None:
            return None
        return self.coordinator.data.coordinates_wgs84[0]

    @property
    def longitude(self) -> float | None:
        """Return WGS84 longitude."""
        if self.coordinator.data is None or self.coordinator.data.coordinates_wgs84 is None:
            return None
        return self.coordinator.data.coordinates_wgs84[1]

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Expose only non-sensitive location metadata."""
        if self.coordinator.data is None:
            return {}
        return {
            "coordinate_system": "WGS84" if self.runtime.convert_coordinates else "GCJ-02",
            "diagnosis_status": self.coordinator.data.diagnosis_status,
        }
