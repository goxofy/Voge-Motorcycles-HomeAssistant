"""Defensive models and parsers for inconsistent VOGE JSON."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .const import KNOWN_ALERT_TYPES
from .model_catalog import VogeVehicleModel, match_vehicle_model
from .util import (
    parse_bounded_float,
    parse_coordinate_pair,
    parse_float,
    parse_int,
    parse_percent,
)


@dataclass(frozen=True, slots=True)
class VehicleSnapshot:
    """A selected vehicle from the modern device list."""

    device_id: str
    device_id_iot: str | None
    amap_device_id: str | None
    device_name: str | None
    product_id: str | None
    product_name: str | None
    vin: str | None
    user_id: str | None
    user_no: str | None
    coordinates_gcj02: tuple[float, float] | None
    formatted_address: str | None
    gps_time: Any
    gps_time_str: str | None
    time_gen: str | None
    device_status: str | None
    lock_status: str | None
    buzzer_status: str | None
    is_can: str | None
    rest_fuel_liters: float | None
    remaining_range_km: float | None
    consumption_per_100km: float | None
    total_mileage_km: float | None
    monthly_mileage_km: float | None
    average_speed_kmh: float | None
    avg_time_raw: Any
    max_speed_kmh: float | None
    duration_month_text: str | None
    harsh_acceleration_count: int | None
    harsh_deceleration_count: int | None
    harsh_steering_count: int | None
    bending_angle_degrees: float | None
    bending_count: int | None
    menu: dict[str, int] = field(default_factory=dict)

    def capability(self, key: str) -> bool | None:
        """Return a server-declared capability state."""
        value = self.menu.get(key)
        if value is None:
            return None
        return value == 1

    def display_name(self, fallback: str | None = None) -> str:
        """Return the best server-backed vehicle display name."""
        return (
            self.device_name
            or self.product_name
            or fallback
            or (f"VOGE product {self.product_id}" if self.product_id else None)
            or "VOGE Motorcycle"
        )

    def catalog_model(self) -> VogeVehicleModel | None:
        """Return an exact match from the observed business model catalog."""
        return match_vehicle_model(self.device_name, self.product_name)


@dataclass(frozen=True, slots=True)
class DiagnosisSnapshot:
    """A normalized union of the app's diagnosis response models."""

    device_id: str | None
    fuel_percentage: float | None
    fuel_percentage_raw: Any
    fuel_percentage_ambiguous_zero: bool
    rest_fuel_liters: float | None
    total_mileage_km: float | None
    voltage: float | None
    coolant_temperature: float | None
    front_tire_pressure: float | None
    rear_tire_pressure: float | None
    front_tire_temperature: float | None
    rear_tire_temperature: float | None
    next_maintenance_mileage_km: float | None
    time_gen: str | None
    rafe: float | None
    can_list: tuple[dict[str, Any], ...]
    menu: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MonthSummary:
    """Current-month summary returned for an explicit modern device ID."""

    device_id: str | None
    average_speed_kmh: float | None
    distance_km: float | None
    duration_raw: Any
    gps_time: Any
    coordinates_gcj02: tuple[float, float] | None


@dataclass(frozen=True, slots=True)
class AlertMessage:
    """A read-only vehicle message."""

    message_id: str | None
    stable_id: str
    module: int | None
    raw_type: int | None
    event_type: str
    mapping_confidence: str
    title: str
    content: Any
    content_plain: str
    create_time: str | None
    if_read: int | None
    member_id: str | None
    param: Any

    def event_payload(self, vehicle_attribution: str) -> dict[str, Any]:
        """Return user-facing event data without altering the server message."""
        return {
            "message_id": self.message_id or self.stable_id,
            "module": self.module,
            "raw_type": self.raw_type,
            "event_type": self.event_type,
            "mapping_confidence": self.mapping_confidence,
            "title": self.title,
            "content": self.content,
            "content_plain": self.content_plain,
            "create_time": self.create_time,
            "param": self.param,
            "if_read": self.if_read,
            "vehicle_attribution": vehicle_attribution,
        }


def _as_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _as_required_string(value: Any) -> str:
    return _as_optional_string(value) or ""


def _parse_menu(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    parsed: dict[str, int] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            continue
        integer = parse_int(raw)
        if integer in {0, 1}:
            parsed[key] = integer
    return parsed


def parse_vehicle(value: Any) -> VehicleSnapshot | None:
    """Parse one modern MotoItem and reject records without a device ID."""
    if not isinstance(value, dict):
        return None
    device_id = _as_optional_string(value.get("deviceId"))
    if not device_id:
        return None

    coordinates = parse_coordinate_pair(value.get("geoLatitude"), value.get("geoLongitude"))
    if coordinates is None:
        coordinates = parse_coordinate_pair(value.get("latitude"), value.get("longitude"))

    return VehicleSnapshot(
        device_id=device_id,
        device_id_iot=_as_optional_string(value.get("deviceIdIot")),
        amap_device_id=_as_optional_string(value.get("amapDeviceId")),
        device_name=_as_optional_string(value.get("deviceName")),
        product_id=_as_optional_string(value.get("productId")),
        product_name=_as_optional_string(value.get("productName")),
        vin=_as_optional_string(value.get("vin")),
        user_id=_as_optional_string(value.get("userId")),
        user_no=_as_optional_string(value.get("userNo")),
        coordinates_gcj02=coordinates,
        formatted_address=_as_optional_string(value.get("formattedAddress")),
        gps_time=value.get("gpsTime"),
        gps_time_str=_as_optional_string(value.get("gpsTimeStr")),
        time_gen=_as_optional_string(value.get("timeGen")),
        device_status=_as_optional_string(value.get("deviceStatus")),
        lock_status=_as_optional_string(value.get("lockStatus")),
        buzzer_status=_as_optional_string(value.get("buzzerStatus")),
        is_can=_as_optional_string(value.get("isCan")),
        rest_fuel_liters=parse_bounded_float(value.get("restFuelLevel"), 0, 100),
        remaining_range_km=parse_bounded_float(value.get("restTrip"), 0, 3000),
        consumption_per_100km=parse_bounded_float(value.get("consumptionPerHundredKM"), 0, 100),
        total_mileage_km=parse_bounded_float(value.get("sumDistance"), 0, 10_000_000),
        monthly_mileage_km=parse_bounded_float(value.get("distanceMo"), 0, 100_000),
        average_speed_kmh=parse_bounded_float(value.get("aveSpeed"), 0, 500),
        avg_time_raw=value.get("avgTime"),
        max_speed_kmh=parse_bounded_float(value.get("maxSpeed"), 0, 500),
        duration_month_text=_as_optional_string(value.get("durationMoStr")),
        harsh_acceleration_count=parse_int(value.get("harshAccelerationCount")),
        harsh_deceleration_count=parse_int(value.get("harshDecelerationCount")),
        harsh_steering_count=parse_int(value.get("harshSteeringCount")),
        bending_angle_degrees=parse_bounded_float(value.get("bendingAngle"), 0, 180),
        bending_count=parse_int(value.get("bendingCount")),
        menu=_parse_menu(value.get("menu")),
    )


def parse_vehicle_list(value: Any) -> list[VehicleSnapshot]:
    """Parse all valid modern vehicles."""
    if not isinstance(value, list):
        return []
    vehicles = [vehicle for item in value if (vehicle := parse_vehicle(item)) is not None]
    return vehicles


def parse_diagnosis(value: Any) -> DiagnosisSnapshot | None:
    """Parse any of the three observed diagnosis response shapes."""
    if not isinstance(value, dict):
        return None

    raw_percent = value.get("fuelPercentage")
    normalized_raw = raw_percent.strip() if isinstance(raw_percent, str) else raw_percent
    can_list = value.get("canList")
    parsed_can_list = tuple(item for item in can_list if isinstance(item, dict)) if isinstance(can_list, list) else ()

    return DiagnosisSnapshot(
        device_id=_as_optional_string(value.get("deviceId")),
        fuel_percentage=parse_percent(raw_percent),
        fuel_percentage_raw=raw_percent,
        fuel_percentage_ambiguous_zero=normalized_raw in {"0", "0%", "0.0", "0.0%"},
        rest_fuel_liters=parse_bounded_float(value.get("restFuelLevel"), 0, 100),
        total_mileage_km=parse_bounded_float(value.get("sumDistance"), 0, 10_000_000),
        voltage=parse_bounded_float(value.get("voltage"), 0, 100),
        coolant_temperature=parse_bounded_float(value.get("coolingTpr"), -50, 250),
        front_tire_pressure=parse_bounded_float(value.get("frontTireP"), 0, 20),
        rear_tire_pressure=parse_bounded_float(value.get("queenTireP"), 0, 20),
        front_tire_temperature=parse_bounded_float(value.get("frontTireTpr"), -50, 250),
        rear_tire_temperature=parse_bounded_float(value.get("queenTireTpr"), -50, 250),
        next_maintenance_mileage_km=parse_bounded_float(value.get("nextUpkeepMileage"), 0, 1_000_000),
        time_gen=_as_optional_string(value.get("timeGen")),
        rafe=parse_float(value.get("rafe")),
        can_list=parsed_can_list,
        menu=_parse_menu(value.get("menu")),
    )


def diagnosis_matches_vehicle(
    diagnosis: DiagnosisSnapshot | None,
    vehicle: VehicleSnapshot,
) -> bool:
    """Require the diagnosis endpoint to identify the selected vehicle exactly."""
    return diagnosis is not None and diagnosis.device_id == vehicle.device_id


def parse_month_summary(value: Any) -> MonthSummary | None:
    """Parse the explicit-device current-month endpoint."""
    if not isinstance(value, dict):
        return None
    coordinates = parse_coordinate_pair(value.get("geoLatitude"), value.get("geoLongitude"))
    return MonthSummary(
        device_id=_as_optional_string(value.get("deviceId")),
        average_speed_kmh=parse_bounded_float(value.get("aveSpeed"), 0, 500),
        distance_km=parse_bounded_float(value.get("distance"), 0, 100_000),
        duration_raw=value.get("duration"),
        gps_time=value.get("gpsTime"),
        coordinates_gcj02=coordinates,
    )


def _parse_json_string(value: str) -> Any:
    stripped = value.strip()
    if len(stripped) > 65_536 or not stripped.startswith(("{", "[")):
        return value
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return value


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return _parse_json_string(value)
    if isinstance(value, (dict, list, int, float, bool)) or value is None:
        return value
    return str(value)


def _plain_content(value: Any) -> str:
    parsed = _normalize_json_value(value)
    if isinstance(parsed, list):
        fragments: list[str] = []
        for item in parsed:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                fragments.append(item["text"])
            elif isinstance(item, str):
                fragments.append(item)
            else:
                return _as_required_string(value)
        return "".join(fragments)
    if isinstance(parsed, str):
        return parsed
    return _as_required_string(value)


def _synthetic_message_id(value: dict[str, Any]) -> str:
    stable_fields = {
        "module": value.get("module"),
        "type": value.get("type"),
        "title": value.get("title"),
        "content": value.get("content"),
        "createTime": value.get("createTime"),
        "param": value.get("param"),
    }
    serialized = json.dumps(stable_fields, ensure_ascii=False, sort_keys=True, default=str)
    return f"synthetic:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def parse_alert_message(value: Any) -> AlertMessage | None:
    """Parse a legacy MessageModel without assuming param semantics."""
    if not isinstance(value, dict):
        return None

    message_id = _as_optional_string(value.get("messageId"))
    raw_type = parse_int(value.get("type"))
    event_type = KNOWN_ALERT_TYPES.get(raw_type, "unknown") if raw_type is not None else "unknown"
    confidence = "icon_only" if raw_type == 50 else ("confirmed_static" if raw_type in KNOWN_ALERT_TYPES else "unknown")
    content = _normalize_json_value(value.get("content"))

    return AlertMessage(
        message_id=message_id,
        stable_id=message_id or _synthetic_message_id(value),
        module=parse_int(value.get("module")),
        raw_type=raw_type,
        event_type=event_type,
        mapping_confidence=confidence,
        title=_as_required_string(value.get("title")),
        content=content,
        content_plain=_plain_content(value.get("content")),
        create_time=_as_optional_string(value.get("createTime")),
        if_read=parse_int(value.get("ifRead")),
        member_id=_as_optional_string(value.get("memberId")),
        param=_normalize_json_value(value.get("param")),
    )


def parse_alert_messages(value: Any) -> list[AlertMessage]:
    """Parse all valid alert records."""
    if not isinstance(value, list):
        return []
    return [message for item in value if (message := parse_alert_message(item)) is not None]


def normalize_vin(value: str | None) -> str | None:
    """Normalize a VIN only for exact identity correlation."""
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def find_unique_legacy_vehicle_id(
    modern_vehicle: VehicleSnapshot,
    legacy_vehicles: Any,
) -> str | None:
    """Return a legacy vehicle ID only for one exact VIN match."""
    modern_vin = normalize_vin(modern_vehicle.vin)
    if not modern_vin or not isinstance(legacy_vehicles, list):
        return None

    matches: list[str] = []
    for vehicle in legacy_vehicles:
        if not isinstance(vehicle, dict):
            continue
        if normalize_vin(_as_optional_string(vehicle.get("vin"))) != modern_vin:
            continue
        vehicle_id = _as_optional_string(vehicle.get("vehicleId"))
        if vehicle_id:
            matches.append(vehicle_id)
    return matches[0] if len(matches) == 1 else None
