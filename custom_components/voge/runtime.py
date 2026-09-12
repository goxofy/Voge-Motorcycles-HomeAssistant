"""Runtime container for one VOGE config entry."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .api import VogeLegacyClient, VogeModernClient
from .auth_manager import VogeAuthManager
from .coordinator import (
    VogeAlertCoordinator,
    VogeStatisticsCoordinator,
    VogeTelemetryCoordinator,
)
from .routes import DayTripSummary, RouteDetail


@dataclass(slots=True)
class VogeRuntimeData:
    """Clients, coordinators, and non-persistent route caches."""

    auth_manager: VogeAuthManager
    modern_client: VogeModernClient
    legacy_client: VogeLegacyClient | None
    telemetry: VogeTelemetryCoordinator
    statistics: VogeStatisticsCoordinator
    alerts: VogeAlertCoordinator | None
    device_id: str
    device_key: str
    account_key: str
    product_name: str
    product_id: str | None
    server_timezone: str
    convert_coordinates: bool
    options_snapshot: dict[str, Any]
    route_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    month_cache: dict[str, tuple[datetime, list[DayTripSummary]]] = field(default_factory=dict)
    route_cache: dict[str, tuple[datetime, RouteDetail]] = field(default_factory=dict)
