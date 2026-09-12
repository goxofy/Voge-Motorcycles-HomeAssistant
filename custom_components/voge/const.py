"""Constants for the VOGE integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "voge"
NAME: Final = "VOGE"
VERSION: Final = "0.1.0"

MODERN_BASE_URL: Final = "https://iot-api.loncinindustries.com"
LEGACY_BASE_URL: Final = "https://voge.loncinindustries.com/api"

CONF_TOKEN: Final = "token"
CONF_AUTH_MODE: Final = "auth_mode"
CONF_MOBILE: Final = "mobile"
CONF_PASSWORD: Final = "password"
CONF_DEVICE_ID: Final = "device_id"
CONF_PRODUCT_NAME: Final = "product_name"
CONF_PRODUCT_ID: Final = "product_id"
CONF_ACCOUNT_KEY: Final = "account_key"

AUTH_MODE_PASSWORD: Final = "password"
AUTH_MODE_TOKEN: Final = "token"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_STATS_INTERVAL: Final = "stats_interval"
CONF_ALERT_INTERVAL: Final = "alert_interval"
CONF_SERVER_TIMEZONE: Final = "server_timezone"
CONF_CONVERT_COORDINATES: Final = "convert_coordinates"
CONF_ENABLE_ALERTS: Final = "enable_alerts"

DEFAULT_SCAN_INTERVAL: Final = 90
DEFAULT_STATS_INTERVAL: Final = 1800
DEFAULT_ALERT_INTERVAL: Final = 45
DEFAULT_SERVER_TIMEZONE: Final = "Asia/Shanghai"
DEFAULT_CONVERT_COORDINATES: Final = True
DEFAULT_ENABLE_ALERTS: Final = True

MIN_SCAN_INTERVAL: Final = 60
MAX_SCAN_INTERVAL: Final = 300
MIN_STATS_INTERVAL: Final = 900
MAX_STATS_INTERVAL: Final = 3600
MIN_ALERT_INTERVAL: Final = 30
MAX_ALERT_INTERVAL: Final = 300

PLATFORMS: Final = ("sensor", "device_tracker", "event")

SERVICE_GET_MONTH_TRIPS: Final = "get_month_trips"
SERVICE_GET_ROUTE_GEOJSON: Final = "get_route_geojson"
SERVICE_GET_DAY_GEOJSON: Final = "get_day_geojson"

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_MONTH: Final = "month"
ATTR_DAY: Final = "day"
ATTR_ROUTE_ID: Final = "route_id"

EVENT_VEHICLE_ALERT: Final = "voge_vehicle_alert"

STORE_VERSION: Final = 1
STORE_KEY_PREFIX: Final = "voge.alerts"
MAX_RECENT_MESSAGE_IDS: Final = 500
ALERT_PAGE_SIZE: Final = 50
ALERT_MAX_PAGES: Final = 5

MODERN_MAX_BODY_BYTES: Final = 2 * 1024 * 1024
ROUTE_MAX_BODY_BYTES: Final = 20 * 1024 * 1024
LEGACY_MAX_BODY_BYTES: Final = 2 * 1024 * 1024

TIMEOUT_SECONDS: Final = 30
ROUTE_TIMEOUT_SECONDS: Final = 60
RATE_LIMIT_FALLBACK_SECONDS: Final = 30
RATE_LIMIT_MAX_SECONDS: Final = 3600

KNOWN_ALERT_TYPES: Final[dict[int, str]] = {
    1: "fault_code",
    2: "safe_riding",
    3: "vibration",
    4: "geofence",
    5: "collision",
    6: "low_voltage",
    7: "low_data",
    8: "anti_theft",
    9: "device_disconnected",
    10: "abnormal_movement",
    13: "low_fuel",
    50: "vibration",
}

EVENT_TYPES: Final = (
    "fault_code",
    "safe_riding",
    "vibration",
    "geofence",
    "collision",
    "low_voltage",
    "low_data",
    "anti_theft",
    "device_disconnected",
    "abnormal_movement",
    "low_fuel",
    "unknown",
)
