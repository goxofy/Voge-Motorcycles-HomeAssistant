"""Read-only account message events for VOGE."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, EVENT_TYPES, EVENT_VEHICLE_ALERT
from .coordinator import VogeAlertCoordinator
from .runtime import VogeRuntimeData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the alert event entity when local legacy signing is available."""
    runtime: VogeRuntimeData = entry.runtime_data
    if runtime.alerts is not None:
        async_add_entities([VogeAlertEvent(runtime)])


class VogeAlertEvent(CoordinatorEntity[VogeAlertCoordinator], EventEntity):
    """Emit each new module-1 message without marking it read."""

    _attr_has_entity_name = True
    _attr_translation_key = "vehicle_alert"
    _attr_event_types = list(EVENT_TYPES)

    def __init__(self, runtime: VogeRuntimeData) -> None:
        if runtime.alerts is None:
            raise ValueError("Alert coordinator is not enabled")
        super().__init__(runtime.alerts)
        self.runtime = runtime
        self._attr_unique_id = f"account_{runtime.account_key}_vehicle_alert"

    @property
    def device_info(self) -> DeviceInfo:
        """Keep account messages on an account-level device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"account_{self.runtime.account_key}")},
            manufacturer="VOGE",
            model="Cloud account",
            name="VOGE Account Alerts",
        )

    def _attribution(self) -> str:
        """Describe attribution without claiming a message identifies the vehicle."""
        data = self.runtime.telemetry.data
        if data is not None and data.bound_vehicle_count == 1:
            return "single_vehicle_assumption"
        return "account_level"

    async def async_added_to_hass(self) -> None:
        """Subscribe before releasing batches fetched during platform setup."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if data is None or not data.messages:
            super()._handle_coordinator_update()
            return

        delivered_ids: list[str] = []
        try:
            for message in data.messages:
                payload = message.event_payload(self._attribution())
                self._trigger_event(message.event_type, payload)
                self.async_write_ha_state()
                self.hass.bus.async_fire(EVENT_VEHICLE_ALERT, payload)
                delivered_ids.append(message.stable_id)
        except Exception:
            self.coordinator.store.release_inflight(
                [message.stable_id for message in data.messages]
            )
            raise

        if delivered_ids:
            self.hass.async_create_task(
                self.coordinator.store.async_acknowledge(delivered_ids),
                "acknowledge_voge_alerts",
            )
