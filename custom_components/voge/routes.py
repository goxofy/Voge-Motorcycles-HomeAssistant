"""Trip, route, and GeoJSON handling for VOGE."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .util import gcj02_to_wgs84, parse_bounded_float, parse_coordinate_pair, parse_int


class RouteParseError(ValueError):
    """Raised when a route cannot be represented safely."""


@dataclass(frozen=True, slots=True)
class TrackPoint:
    """One GCJ-02 route point."""

    latitude: float
    longitude: float
    speed_kmh: float | None
    direction_degrees: float | None
    locatetime_raw: int | None


@dataclass(frozen=True, slots=True)
class TripSummary:
    """One trip returned inside a monthly day group."""

    route_id: str
    day: str | None
    begin_date: str | None
    end_date: str | None
    begin_address: str | None
    end_address: str | None
    begin_coordinates_gcj02: tuple[float, float] | None
    end_coordinates_gcj02: tuple[float, float] | None
    distance_km: float | None
    duration_raw: Any
    duration_text: str | None
    average_speed_kmh: float | None
    max_speed_kmh: float | None
    accumulation: int | None
    bending_angle_degrees: float | None
    bending_count: int | None


@dataclass(frozen=True, slots=True)
class DayTripSummary:
    """Server-provided daily group from a monthly track request."""

    day: str
    distance_km: float | None
    duration_raw: Any
    duration_text: str | None
    trip_count: int | None
    average_speed_kmh: float | None
    max_speed_kmh: float | None
    bending_angle_degrees: float | None
    bending_count: int | None
    trips: tuple[TripSummary, ...]


@dataclass(frozen=True, slots=True)
class RouteDetail:
    """One verified route detail response."""

    route_id: str
    begin_address: str | None
    end_address: str | None
    created_at: str | None
    distance_km: float | None
    duration_raw: Any
    duration_text: str | None
    max_speed_kmh: float | None
    total_mileage_km: float | None
    points: tuple[TrackPoint, ...]


def _string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def parse_trip_summary(value: Any) -> TripSummary | None:
    """Parse one MotoTrackItem."""
    if not isinstance(value, dict):
        return None
    route_id = _string(value.get("routeId"))
    if not route_id:
        return None
    return TripSummary(
        route_id=route_id,
        day=_string(value.get("day")),
        begin_date=_string(value.get("beginDate")),
        end_date=_string(value.get("endDate")),
        begin_address=_string(value.get("beginAddr")),
        end_address=_string(value.get("endAddr")),
        begin_coordinates_gcj02=parse_coordinate_pair(value.get("beginLatitude"), value.get("beginLongitude")),
        end_coordinates_gcj02=parse_coordinate_pair(value.get("endLatitude"), value.get("endLongitude")),
        distance_km=parse_bounded_float(value.get("distanceMo"), 0, 100_000),
        duration_raw=value.get("durationMo"),
        duration_text=_string(value.get("durationMoStr")),
        average_speed_kmh=parse_bounded_float(value.get("aveSpeed"), 0, 500),
        max_speed_kmh=parse_bounded_float(value.get("maxSpeed"), 0, 500),
        accumulation=parse_int(value.get("accumulation")),
        bending_angle_degrees=parse_bounded_float(value.get("bendingAngle"), 0, 180),
        bending_count=parse_int(value.get("bendingCount")),
    )


def parse_month_tracks(value: Any) -> list[DayTripSummary]:
    """Parse the modern monthly trip-list response."""
    if not isinstance(value, list):
        return []
    groups: list[DayTripSummary] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        day = _string(item.get("day"))
        if not day:
            continue
        raw_trips = item.get("list")
        trips = (
            tuple(trip for raw in raw_trips if (trip := parse_trip_summary(raw)) is not None)
            if isinstance(raw_trips, list)
            else ()
        )
        groups.append(
            DayTripSummary(
                day=day,
                distance_km=parse_bounded_float(item.get("distanceMo"), 0, 100_000),
                duration_raw=item.get("durationMo"),
                duration_text=_string(item.get("durationMoStr")),
                trip_count=parse_int(item.get("driveTotalTimes")),
                average_speed_kmh=parse_bounded_float(item.get("aveSpeed"), 0, 500),
                max_speed_kmh=parse_bounded_float(item.get("maxSpeed"), 0, 500),
                bending_angle_degrees=parse_bounded_float(item.get("bendingAngle"), 0, 180),
                bending_count=parse_int(item.get("bendingCount")),
                trips=trips,
            )
        )
    return groups


def route_ids_for_month(groups: list[DayTripSummary]) -> set[str]:
    """Return the only route IDs that may be used for detail requests."""
    return {trip.route_id for group in groups for trip in group.trips}


def route_ids_for_day(groups: list[DayTripSummary], day: str) -> list[str]:
    """Return verified route IDs for an exact server-provided day string."""
    return [trip.route_id for group in groups if group.day == day for trip in group.trips]


def parse_track_point(value: Any) -> TrackPoint | None:
    """Parse one route point and reject invalid coordinates."""
    if not isinstance(value, dict):
        return None
    coordinates = parse_coordinate_pair(value.get("lat"), value.get("lon"))
    if coordinates is None:
        return None
    locatetime = parse_int(value.get("locatetime"))
    return TrackPoint(
        latitude=coordinates[0],
        longitude=coordinates[1],
        speed_kmh=parse_bounded_float(value.get("speed"), 0, 500),
        direction_degrees=parse_bounded_float(value.get("direction"), 0, 360),
        locatetime_raw=locatetime,
    )


def _decode_points(value: Any) -> list[Any]:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            decoded = json.loads(stripped)
        except (json.JSONDecodeError, ValueError) as err:
            raise RouteParseError("route_points_invalid_json") from err
    else:
        decoded = value
    if not isinstance(decoded, list):
        raise RouteParseError("route_points_not_array")
    return decoded


def parse_route_detail(value: Any, expected_route_id: str) -> RouteDetail:
    """Parse route detail and enforce request/response identity."""
    if not isinstance(value, dict):
        raise RouteParseError("route_detail_not_object")

    response_route_id = _string(value.get("routeId"))
    if response_route_id and response_route_id != expected_route_id:
        raise RouteParseError("route_id_mismatch")

    raw_points = _decode_points(value.get("points"))
    points = tuple(point for item in raw_points if (point := parse_track_point(item)) is not None)
    if len(points) < 2:
        raise RouteParseError("route_has_fewer_than_two_valid_points")

    return RouteDetail(
        route_id=response_route_id or expected_route_id,
        begin_address=_string(value.get("beginAddr")),
        end_address=_string(value.get("endAddr")),
        created_at=_string(value.get("crtDate")),
        distance_km=parse_bounded_float(value.get("distanceMo"), 0, 100_000),
        duration_raw=value.get("durationMo"),
        duration_text=_string(value.get("durationMoStr")),
        max_speed_kmh=parse_bounded_float(value.get("maxSpeed"), 0, 500),
        total_mileage_km=parse_bounded_float(value.get("sumDistance"), 0, 10_000_000),
        points=points,
    )


def _point_coordinates(point: TrackPoint, convert_coordinates: bool) -> list[float]:
    latitude, longitude = point.latitude, point.longitude
    if convert_coordinates:
        latitude, longitude = gcj02_to_wgs84(latitude, longitude)
    return [longitude, latitude]


def route_to_geojson(route: RouteDetail, convert_coordinates: bool) -> dict[str, Any]:
    """Build a GeoJSON Feature without connecting independent routes."""
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [
                _point_coordinates(point, convert_coordinates) for point in route.points
            ],
        },
        "properties": {
            "route_id": route.route_id,
            "begin_address": route.begin_address,
            "end_address": route.end_address,
            "created_at": route.created_at,
            "distance_km": route.distance_km,
            "duration_raw": route.duration_raw,
            "duration_text": route.duration_text,
            "max_speed_kmh": route.max_speed_kmh,
            "total_mileage_km": route.total_mileage_km,
            "coordinate_system": "WGS84" if convert_coordinates else "GCJ-02",
            "point_count": len(route.points),
        },
    }


def day_routes_to_geojson(
    day: str,
    routes: list[RouteDetail],
    convert_coordinates: bool,
    *,
    partial: bool = False,
    error_count: int = 0,
) -> dict[str, Any]:
    """Build one LineString feature per trip and retain every segment boundary."""
    return {
        "type": "FeatureCollection",
        "features": [route_to_geojson(route, convert_coordinates) for route in routes],
        "properties": {
            "day": day,
            "route_count": len(routes),
            "partial": partial,
            "error_count": error_count,
            "coordinate_system": "WGS84" if convert_coordinates else "GCJ-02",
        },
    }


def month_tracks_to_dict(groups: list[DayTripSummary]) -> dict[str, Any]:
    """Return service-safe structured monthly trip summaries."""
    return {
        "days": [
            {
                "day": group.day,
                "distance_km": group.distance_km,
                "duration_raw": group.duration_raw,
                "duration_text": group.duration_text,
                "trip_count": group.trip_count,
                "average_speed_kmh": group.average_speed_kmh,
                "max_speed_kmh": group.max_speed_kmh,
                "bending_angle_degrees": group.bending_angle_degrees,
                "bending_count": group.bending_count,
                "trips": [
                    {
                        "route_id": trip.route_id,
                        "begin_date": trip.begin_date,
                        "end_date": trip.end_date,
                        "begin_address": trip.begin_address,
                        "end_address": trip.end_address,
                        "distance_km": trip.distance_km,
                        "duration_raw": trip.duration_raw,
                        "duration_text": trip.duration_text,
                        "average_speed_kmh": trip.average_speed_kmh,
                        "max_speed_kmh": trip.max_speed_kmh,
                        "accumulation": trip.accumulation,
                        "bending_angle_degrees": trip.bending_angle_degrees,
                        "bending_count": trip.bending_count,
                    }
                    for trip in group.trips
                ],
            }
            for group in groups
        ]
    }
