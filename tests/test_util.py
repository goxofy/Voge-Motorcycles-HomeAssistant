"""Numeric, timestamp, and coordinate conversion tests."""

from datetime import UTC, datetime

from custom_components.voge.util import (
    gcj02_to_wgs84,
    parse_coordinate_pair,
    parse_float,
    parse_int,
    parse_server_datetime,
    wgs84_to_gcj02,
)


def test_numeric_parser_rejects_non_finite_and_bool() -> None:
    assert parse_float("3.14") == 3.14
    assert parse_float(float("nan")) is None
    assert parse_float("inf") is None
    assert parse_float(True) is None
    assert parse_int("2") == 2
    assert parse_int("2.5") is None


def test_coordinate_pair_rejects_ranges_and_null_island() -> None:
    assert parse_coordinate_pair("29", "106") == (29.0, 106.0)
    assert parse_coordinate_pair(91, 106) is None
    assert parse_coordinate_pair(0, 0) is None


def test_gcj_inverse_round_trip_in_mainland_china() -> None:
    wgs = (29.5630, 106.5516)
    gcj = wgs84_to_gcj02(*wgs)
    restored = gcj02_to_wgs84(*gcj)
    assert abs(restored[0] - wgs[0]) < 1e-6
    assert abs(restored[1] - wgs[1]) < 1e-6


def test_coordinates_outside_china_are_unchanged() -> None:
    london = (51.5074, -0.1278)
    assert gcj02_to_wgs84(*london) == london


def test_server_time_uses_configured_timezone_not_utc_assumption() -> None:
    parsed = parse_server_datetime("2026-09-11 12:00:00", "Asia/Shanghai")
    assert parsed == datetime(2026, 9, 11, 4, 0, tzinfo=UTC)
    assert parse_server_datetime("invalid", "Asia/Shanghai") is None
    assert parse_server_datetime("2026-09-11 12:00:00", "Not/AZone") is None
