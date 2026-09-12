"""Route identity, segmentation, and coordinate-order tests."""

import pytest

from custom_components.voge.routes import (
    RouteParseError,
    day_routes_to_geojson,
    parse_month_tracks,
    parse_route_detail,
    route_ids_for_day,
    route_ids_for_month,
    route_to_geojson,
)


def _groups():
    return parse_month_tracks(
        [
            {
                "day": "server-day-A",
                "distanceMo": "12.5",
                "driveTotalTimes": 2,
                "list": [
                    {"routeId": "r1", "distanceMo": "5.0"},
                    {"routeId": "r2", "distanceMo": "7.5"},
                ],
            },
            {
                "day": "server-day-B",
                "list": [{"routeId": "r3"}],
            },
        ]
    )


def _detail(route_id: str, offset: float = 0):
    return parse_route_detail(
        {
            "routeId": route_id,
            "points": (
                '[{"lat":"29.0","lon":"106.0","speed":10,"locatetime":123},'
                f'{{"lat":"{29.1 + offset}","lon":"{106.1 + offset}","speed":20}}]'
            ),
        },
        route_id,
    )


def test_route_ids_can_only_come_from_month_response() -> None:
    groups = _groups()
    assert route_ids_for_month(groups) == {"r1", "r2", "r3"}
    assert route_ids_for_day(groups, "server-day-A") == ["r1", "r2"]
    assert route_ids_for_day(groups, "2026-09-11") == []


def test_route_detail_rejects_identity_mismatch() -> None:
    with pytest.raises(RouteParseError, match="route_id_mismatch"):
        parse_route_detail(
            {
                "routeId": "other",
                "points": '[{"lat":"29","lon":"106"},{"lat":"29.1","lon":"106.1"}]',
            },
            "expected",
        )


def test_route_points_are_double_encoded_and_geojson_is_lon_lat() -> None:
    route = _detail("r1")
    feature = route_to_geojson(route, convert_coordinates=False)
    assert feature["geometry"]["coordinates"][0] == [106.0, 29.0]
    assert route.points[0].locatetime_raw == 123


def test_day_geojson_preserves_two_route_segments() -> None:
    collection = day_routes_to_geojson(
        "server-day-A",
        [_detail("r1"), _detail("r2", 0.5)],
        convert_coordinates=False,
    )
    assert collection["type"] == "FeatureCollection"
    assert len(collection["features"]) == 2
    assert all(feature["geometry"]["type"] == "LineString" for feature in collection["features"])


def test_invalid_route_segment_fails_without_printing_raw_points() -> None:
    with pytest.raises(RouteParseError, match="route_points_invalid_json"):
        parse_route_detail({"routeId": "r1", "points": "[{secret"}, "r1")
