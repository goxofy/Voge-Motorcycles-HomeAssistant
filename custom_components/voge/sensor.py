"""Sensors for read-only VOGE motorcycle telemetry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import StatisticsData, TelemetryData, VogeStatisticsCoordinator
from .entity import VogeTelemetryEntity, vehicle_device_info
from .runtime import VogeRuntimeData
from .util import parse_server_datetime

ValueFn = Callable[[TelemetryData, VogeRuntimeData], Any]
StatisticsValueFn = Callable[[StatisticsData, VogeRuntimeData], Any]


@dataclass(frozen=True, kw_only=True)
class VogeSensorDescription(SensorEntityDescription):
    """Describe a VOGE sensor and its defensive value selector."""

    value_fn: ValueFn
    capability_key: str | None = None
    enable_without_capability: bool = True


@dataclass(frozen=True, kw_only=True)
class VogeStatisticsSensorDescription(SensorEntityDescription):
    """Describe a sensor from the explicit-device monthly summary."""

    value_fn: StatisticsValueFn


def _diagnosis_value(attribute: str) -> ValueFn:
    def value(data: TelemetryData, runtime: VogeRuntimeData) -> Any:
        if data.diagnosis is None:
            return None
        return getattr(data.diagnosis, attribute)

    return value


def _vehicle_value(attribute: str) -> ValueFn:
    return lambda data, runtime: getattr(data.vehicle, attribute)


def _prefer_diagnosis(diagnosis_attr: str, vehicle_attr: str) -> ValueFn:
    def value(data: TelemetryData, runtime: VogeRuntimeData) -> Any:
        if data.diagnosis is not None:
            diagnosis_value = getattr(data.diagnosis, diagnosis_attr)
            if diagnosis_value is not None:
                return diagnosis_value
        return getattr(data.vehicle, vehicle_attr)

    return value


def _fuel_percentage(data: TelemetryData, runtime: VogeRuntimeData) -> float | None:
    diagnosis = data.diagnosis
    if diagnosis is None or diagnosis.fuel_percentage_ambiguous_zero:
        return None
    return diagnosis.fuel_percentage


def _gps_timestamp(data: TelemetryData, runtime: VogeRuntimeData) -> datetime | None:
    raw = data.vehicle.gps_time_str
    if raw is None and isinstance(data.vehicle.gps_time, str):
        raw = data.vehicle.gps_time
    return parse_server_datetime(raw, runtime.server_timezone)


def _vehicle_timestamp(data: TelemetryData, runtime: VogeRuntimeData) -> datetime | None:
    raw = data.diagnosis.time_gen if data.diagnosis is not None else data.vehicle.time_gen
    return parse_server_datetime(raw, runtime.server_timezone)


SENSORS: tuple[VogeSensorDescription, ...] = (
    VogeSensorDescription(
        key="fuel_percentage",
        translation_key="fuel_percentage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_fuel_percentage,
        capability_key="fuelPercentage",
    ),
    VogeSensorDescription(
        key="remaining_fuel",
        translation_key="remaining_fuel",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_prefer_diagnosis("rest_fuel_liters", "rest_fuel_liters"),
        capability_key="restFuelLevel",
    ),
    VogeSensorDescription(
        key="fuel_consumption",
        translation_key="fuel_consumption",
        native_unit_of_measurement="L/100 km",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_vehicle_value("consumption_per_100km"),
        capability_key="consumptionPerHundredKM",
    ),
    VogeSensorDescription(
        key="remaining_range",
        translation_key="remaining_range",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_vehicle_value("remaining_range_km"),
        capability_key="restTrip",
    ),
    VogeSensorDescription(
        key="total_mileage",
        translation_key="total_mileage",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_prefer_diagnosis("total_mileage_km", "total_mileage_km"),
        capability_key="sumDistance",
    ),
    VogeSensorDescription(
        key="maximum_speed",
        translation_key="maximum_speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_vehicle_value("max_speed_kmh"),
    ),
    VogeSensorDescription(
        key="monthly_duration",
        translation_key="monthly_duration",
        value_fn=_vehicle_value("duration_month_text"),
    ),
    VogeSensorDescription(
        key="voltage",
        translation_key="voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_diagnosis_value("voltage"),
        capability_key="voltage",
    ),
    VogeSensorDescription(
        key="coolant_temperature",
        translation_key="coolant_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_diagnosis_value("coolant_temperature"),
        capability_key="coolingTpr",
        enable_without_capability=False,
    ),
    VogeSensorDescription(
        key="front_tire_pressure",
        translation_key="front_tire_pressure",
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_diagnosis_value("front_tire_pressure"),
        capability_key="frontTireP",
        enable_without_capability=False,
    ),
    VogeSensorDescription(
        key="rear_tire_pressure",
        translation_key="rear_tire_pressure",
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_diagnosis_value("rear_tire_pressure"),
        capability_key="queenTireP",
        enable_without_capability=False,
    ),
    VogeSensorDescription(
        key="front_tire_temperature",
        translation_key="front_tire_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_diagnosis_value("front_tire_temperature"),
        capability_key="frontTireTpr",
        enable_without_capability=False,
    ),
    VogeSensorDescription(
        key="rear_tire_temperature",
        translation_key="rear_tire_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_diagnosis_value("rear_tire_temperature"),
        capability_key="queenTireTpr",
        enable_without_capability=False,
    ),
    VogeSensorDescription(
        key="next_maintenance_mileage",
        translation_key="next_maintenance_mileage",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_diagnosis_value("next_maintenance_mileage_km"),
        capability_key="nextUpkeepMileage",
        enable_without_capability=False,
    ),
    VogeSensorDescription(
        key="harsh_acceleration_count",
        translation_key="harsh_acceleration_count",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_vehicle_value("harsh_acceleration_count"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VogeSensorDescription(
        key="harsh_deceleration_count",
        translation_key="harsh_deceleration_count",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_vehicle_value("harsh_deceleration_count"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VogeSensorDescription(
        key="harsh_steering_count",
        translation_key="harsh_steering_count",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_vehicle_value("harsh_steering_count"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VogeSensorDescription(
        key="bending_count",
        translation_key="bending_count",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_vehicle_value("bending_count"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VogeSensorDescription(
        key="bending_angle",
        translation_key="bending_angle",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_vehicle_value("bending_angle_degrees"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VogeSensorDescription(
        key="gps_update_time",
        translation_key="gps_update_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_gps_timestamp,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VogeSensorDescription(
        key="vehicle_update_time",
        translation_key="vehicle_update_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_vehicle_timestamp,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VogeSensorDescription(
        key="cloud_fetch_time",
        translation_key="cloud_fetch_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data, runtime: data.fetched_at,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

STATISTICS_SENSORS: tuple[VogeStatisticsSensorDescription, ...] = (
    VogeStatisticsSensorDescription(
        key="monthly_mileage",
        translation_key="monthly_mileage",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data, runtime: (
            data.summary.distance_km
            if data.summary is not None and data.summary.distance_km is not None
            else (
                runtime.telemetry.data.vehicle.monthly_mileage_km
                if runtime.telemetry.data is not None
                else None
            )
        ),
    ),
    VogeStatisticsSensorDescription(
        key="average_speed",
        translation_key="average_speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data, runtime: (
            data.summary.average_speed_kmh
            if data.summary is not None and data.summary.average_speed_kmh is not None
            else (
                runtime.telemetry.data.vehicle.average_speed_kmh
                if runtime.telemetry.data is not None
                else None
            )
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VOGE sensors."""
    runtime: VogeRuntimeData = entry.runtime_data
    async_add_entities(VogeSensor(runtime, description) for description in SENSORS)
    async_add_entities(
        VogeStatisticsSensor(runtime, description) for description in STATISTICS_SENSORS
    )


class VogeSensor(VogeTelemetryEntity, SensorEntity):
    """A defensive coordinator-backed VOGE sensor."""

    entity_description: VogeSensorDescription

    def __init__(self, runtime: VogeRuntimeData, description: VogeSensorDescription) -> None:
        super().__init__(runtime, description.key)
        self.entity_description = description
        capability = self._capability_state()
        if capability is None and not description.enable_without_capability:
            self._attr_entity_registry_enabled_default = False

    def _capability_state(self) -> bool | None:
        key = self.entity_description.capability_key
        if key is None or self.coordinator.data is None:
            return None
        diagnosis = self.coordinator.data.diagnosis
        if diagnosis is not None and key in diagnosis.menu:
            return diagnosis.menu[key] == 1
        return self.coordinator.data.vehicle.capability(key)

    @property
    def available(self) -> bool:
        """Use unavailable for unsupported fields and unknown for empty supported fields."""
        if not super().available or self.coordinator.data is None:
            return False
        capability = self._capability_state()
        if capability is False and not self.entity_description.enable_without_capability:
            return False
        if capability is True:
            return True
        return self.native_value is not None

    @property
    def native_value(self) -> Any:
        """Return one normalized value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data, self.runtime)


class VogeStatisticsSensor(CoordinatorEntity[VogeStatisticsCoordinator], SensorEntity):
    """A sensor backed by the explicit-device current-month endpoint."""

    _attr_has_entity_name = True
    entity_description: VogeStatisticsSensorDescription

    def __init__(
        self,
        runtime: VogeRuntimeData,
        description: VogeStatisticsSensorDescription,
    ) -> None:
        super().__init__(runtime.statistics)
        self.runtime = runtime
        self.entity_description = description
        self._attr_unique_id = f"{runtime.device_key}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Attach monthly statistics to the selected motorcycle."""
        return vehicle_device_info(self.runtime)

    @property
    def available(self) -> bool:
        """Require either explicit monthly data or a safe M1 fallback."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.native_value is not None
        )

    @property
    def native_value(self) -> Any:
        """Return explicit-device monthly data, falling back to M1 if absent."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data, self.runtime)
