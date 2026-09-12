"""Pure utility helpers for VOGE data."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_GCJ_A = 6378245.0
_GCJ_EE = 0.00669342162296594323


def stable_hash(value: str, length: int = 16) -> str:
    """Return a non-reversible stable identifier prefix."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def redact_identifier(value: str | None) -> str | None:
    """Replace an identifier with a stable diagnostic-safe marker."""
    if not value:
        return None
    return f"sha256:{stable_hash(value, 12)}…"


def parse_float(value: Any) -> float | None:
    """Parse a finite float from inconsistent backend JSON."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.lower() in {"null", "none", "nan", "-"}:
            return None
        try:
            parsed = float(stripped)
        except ValueError:
            return None
    else:
        return None
    return parsed if math.isfinite(parsed) else None


def parse_int(value: Any) -> int | None:
    """Parse an integer without silently truncating fractional values."""
    parsed = parse_float(value)
    if parsed is None or not parsed.is_integer():
        return None
    return int(parsed)


def parse_percent(value: Any) -> float | None:
    """Parse a percentage represented as a number or percent string."""
    if isinstance(value, str):
        value = value.strip().removesuffix("%").strip()
    parsed = parse_float(value)
    if parsed is None or not 0 <= parsed <= 100:
        return None
    return parsed


def parse_bounded_float(
    value: Any,
    minimum: float,
    maximum: float,
) -> float | None:
    """Parse a finite float and apply a conservative validity range."""
    parsed = parse_float(value)
    if parsed is None or not minimum <= parsed <= maximum:
        return None
    return parsed


def parse_coordinate_pair(
    latitude: Any,
    longitude: Any,
) -> tuple[float, float] | None:
    """Parse and range-check a latitude/longitude pair."""
    lat = parse_bounded_float(latitude, -90.0, 90.0)
    lon = parse_bounded_float(longitude, -180.0, 180.0)
    if lat is None or lon is None:
        return None
    if lat == 0 and lon == 0:
        return None
    return lat, lon


def _out_of_china(latitude: float, longitude: float) -> bool:
    return not (72.004 <= longitude <= 137.8347 and 0.8293 <= latitude <= 55.8271)


def _transform_latitude(x: float, y: float) -> float:
    result = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y
    result += 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    result += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    result += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    result += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return result


def _transform_longitude(x: float, y: float) -> float:
    result = 300.0 + x + 2.0 * y + 0.1 * x * x
    result += 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    result += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    result += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    result += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return result


def wgs84_to_gcj02(latitude: float, longitude: float) -> tuple[float, float]:
    """Convert WGS84 to GCJ-02 for validation and inverse iteration."""
    if _out_of_china(latitude, longitude):
        return latitude, longitude

    delta_lat = _transform_latitude(longitude - 105.0, latitude - 35.0)
    delta_lon = _transform_longitude(longitude - 105.0, latitude - 35.0)
    rad_lat = latitude / 180.0 * math.pi
    magic = math.sin(rad_lat)
    magic = 1 - _GCJ_EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    delta_lat = delta_lat * 180.0 / (
        (_GCJ_A * (1 - _GCJ_EE)) / (magic * sqrt_magic) * math.pi
    )
    delta_lon = delta_lon * 180.0 / (
        _GCJ_A / sqrt_magic * math.cos(rad_lat) * math.pi
    )
    return latitude + delta_lat, longitude + delta_lon


def gcj02_to_wgs84(latitude: float, longitude: float) -> tuple[float, float]:
    """Convert GCJ-02 to WGS84 using a short inverse iteration."""
    if _out_of_china(latitude, longitude):
        return latitude, longitude

    guess_lat = latitude
    guess_lon = longitude
    for _ in range(6):
        converted_lat, converted_lon = wgs84_to_gcj02(guess_lat, guess_lon)
        guess_lat -= converted_lat - latitude
        guess_lon -= converted_lon - longitude
    return guess_lat, guess_lon


def parse_server_datetime(value: Any, timezone_name: str) -> datetime | None:
    """Parse a backend timestamp that may not carry timezone information."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None

    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return None

    parsed: datetime | None = None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(text, pattern)
            break
        except ValueError:
            continue

    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.astimezone(UTC)


def get_first(mapping: dict[str, Any], *keys: str) -> Any:
    """Return the first present non-null value from a mapping."""
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None
