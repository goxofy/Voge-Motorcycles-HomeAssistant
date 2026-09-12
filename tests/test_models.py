"""Defensive VOGE model tests using fully synthetic data."""

from custom_components.voge.models import (
    diagnosis_matches_vehicle,
    find_unique_legacy_vehicle_id,
    parse_alert_message,
    parse_diagnosis,
    parse_vehicle,
)


def _vehicle() -> dict:
    return {
        "deviceId": "modern-1",
        "deviceIdIot": "opaque-iot",
        "productName": "Synthetic CU",
        "vin": "TESTVIN123",
        "geoLatitude": "29.123",
        "geoLongitude": "106.456",
        "restFuelLevel": "7.5",
        "restTrip": 210,
        "consumptionPerHundredKM": "3.1",
        "sumDistance": "1234",
        "distanceMo": 98.5,
        "menu": {
            "restFuelLevel": 1,
            "sumDistance": "1",
            "frontTireP": 0,
            "unexpectedCapability": 2,
        },
    }


def test_vehicle_parses_numeric_strings_and_menu() -> None:
    vehicle = parse_vehicle(_vehicle())
    assert vehicle is not None
    assert vehicle.rest_fuel_liters == 7.5
    assert vehicle.remaining_range_km == 210
    assert vehicle.consumption_per_100km == 3.1
    assert vehicle.total_mileage_km == 1234
    assert vehicle.monthly_mileage_km == 98.5
    assert vehicle.capability("restFuelLevel") is True
    assert vehicle.capability("frontTireP") is False
    assert vehicle.capability("unexpectedCapability") is None
    assert vehicle.capability("missing") is None


def test_vehicle_display_name_prefers_device_name() -> None:
    vehicle = parse_vehicle(
        {
            "deviceId": "modern-1",
            "deviceName": "CU250 II代自动挡",
            "productName": "CU250 family",
            "productId": "2",
        }
    )
    assert vehicle is not None
    assert vehicle.display_name() == "CU250 II代自动挡"
    assert vehicle.catalog_model() is not None
    assert vehicle.catalog_model().model_code == "997"  # type: ignore[union-attr]


def test_vehicle_display_name_falls_back_to_saved_name_then_product_id() -> None:
    vehicle = parse_vehicle({"deviceId": "modern-1", "productId": "2"})
    assert vehicle is not None
    assert vehicle.display_name("Saved model") == "Saved model"
    assert vehicle.display_name() == "VOGE product 2"


def test_catalog_matching_never_interprets_modern_product_id_as_model_code() -> None:
    vehicle = parse_vehicle({"deviceId": "modern-1", "productId": "997"})
    assert vehicle is not None
    assert vehicle.catalog_model() is None


def test_vehicle_rejects_missing_device_id_and_invalid_coordinates() -> None:
    raw = _vehicle()
    raw.pop("deviceId")
    assert parse_vehicle(raw) is None

    raw = _vehicle()
    raw["geoLatitude"] = "999"
    assert parse_vehicle(raw).coordinates_gcj02 is None  # type: ignore[union-attr]


def test_diagnosis_requires_exact_modern_device_id() -> None:
    vehicle = parse_vehicle(_vehicle())
    assert vehicle is not None
    matched = parse_diagnosis({"deviceId": "modern-1", "voltage": "12.7"})
    mismatched = parse_diagnosis({"deviceId": "another", "voltage": 12.7})
    missing = parse_diagnosis({"voltage": 12.7})
    assert diagnosis_matches_vehicle(matched, vehicle)
    assert not diagnosis_matches_vehicle(mismatched, vehicle)
    assert not diagnosis_matches_vehicle(missing, vehicle)


def test_ambiguous_zero_percent_is_flagged() -> None:
    diagnosis = parse_diagnosis(
        {
            "deviceId": "modern-1",
            "fuelPercentage": "0%",
            "restFuelLevel": "3.0",
            "frontTireP": "2.25",
            "queenTireP": 2.4,
        }
    )
    assert diagnosis is not None
    assert diagnosis.fuel_percentage == 0
    assert diagnosis.fuel_percentage_ambiguous_zero
    assert diagnosis.rest_fuel_liters == 3
    assert diagnosis.front_tire_pressure == 2.25
    assert diagnosis.rear_tire_pressure == 2.4


def test_alert_preserves_unknown_type_and_parses_json_strings() -> None:
    alert = parse_alert_message(
        {
            "messageId": "msg-1",
            "module": 1,
            "type": 61,
            "title": "Synthetic alert",
            "content": '[{"text":"part 1"},{"text":" part 2"}]',
            "createTime": "2026-09-11 12:00:00",
            "param": '{"opaque":"value"}',
            "ifRead": 0,
        }
    )
    assert alert is not None
    assert alert.event_type == "unknown"
    assert alert.raw_type == 61
    assert alert.content_plain == "part 1 part 2"
    assert alert.param == {"opaque": "value"}


def test_missing_message_id_uses_non_plaintext_hash() -> None:
    alert = parse_alert_message(
        {
            "module": 1,
            "type": 3,
            "title": "Synthetic vibration",
            "content": "sensitive content",
            "createTime": "2026-09-11 12:00:00",
        }
    )
    assert alert is not None
    assert alert.stable_id.startswith("synthetic:")
    assert "sensitive" not in alert.stable_id


def test_unique_legacy_join_uses_exact_normalized_vin_only() -> None:
    vehicle = parse_vehicle(_vehicle())
    assert vehicle is not None
    assert find_unique_legacy_vehicle_id(
        vehicle,
        [{"vin": " testvin123 ", "vehicleId": "legacy-1"}],
    ) == "legacy-1"
    assert find_unique_legacy_vehicle_id(
        vehicle,
        [
            {"vin": "TESTVIN123", "vehicleId": "legacy-1"},
            {"vin": "TESTVIN123", "vehicleId": "legacy-2"},
        ],
    ) is None
    assert find_unique_legacy_vehicle_id(
        vehicle,
        [{"vin": "TESTVIN124", "vehicleId": "legacy-1"}],
    ) is None
