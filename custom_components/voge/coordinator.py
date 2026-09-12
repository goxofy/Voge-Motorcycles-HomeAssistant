"""Home Assistant data coordinators for VOGE."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VogeApiError, VogeAuthError, VogeLegacyClient, VogeModernClient
from .const import ALERT_MAX_PAGES, ALERT_PAGE_SIZE
from .models import (
    AlertMessage,
    DiagnosisSnapshot,
    MonthSummary,
    VehicleSnapshot,
    diagnosis_matches_vehicle,
    parse_alert_messages,
    parse_diagnosis,
    parse_month_summary,
    parse_vehicle_list,
)
from .store import AlertDedupStore
from .util import gcj02_to_wgs84, parse_int

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TelemetryData:
    """One atomic modern telemetry update."""

    vehicle: VehicleSnapshot
    diagnosis: DiagnosisSnapshot | None
    coordinates_wgs84: tuple[float, float] | None
    fetched_at: datetime
    bound_vehicle_count: int
    diagnosis_status: str


@dataclass(frozen=True, slots=True)
class StatisticsData:
    """Slow current-month data."""

    summary: MonthSummary | None
    month: str
    fetched_at: datetime


@dataclass(frozen=True, slots=True)
class AlertData:
    """Only newly discovered account message events."""

    messages: tuple[AlertMessage, ...]
    fetched_at: datetime
    page_scan_truncated: bool
    server_pages: int | None
    server_total: int | None


class VogeTelemetryCoordinator(DataUpdateCoordinator[TelemetryData]):
    """Fetch selected modern vehicle data and identity-checked diagnosis."""

    def __init__(
        self,
        hass: Any,
        entry: ConfigEntry,
        client: VogeModernClient,
        device_id: str,
        *,
        interval_seconds: int,
        convert_coordinates: bool,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"voge_telemetry_{entry.entry_id}",
            update_interval=timedelta(seconds=interval_seconds),
        )
        self.client = client
        self.device_id = device_id
        self.convert_coordinates = convert_coordinates

    async def _async_update_data(self) -> TelemetryData:
        try:
            raw_devices = await self.client.get_devices()
        except VogeAuthError as err:
            raise ConfigEntryAuthFailed("VOGE token is no longer valid") from err
        except VogeApiError as err:
            raise UpdateFailed(str(err)) from err

        vehicles = parse_vehicle_list(raw_devices)
        vehicle = next((item for item in vehicles if item.device_id == self.device_id), None)
        if vehicle is None:
            raise UpdateFailed("The configured VOGE vehicle was not returned by the account")

        diagnosis: DiagnosisSnapshot | None = None
        diagnosis_status = "not_requested"
        try:
            candidate = parse_diagnosis(await self.client.get_diagnosis())
        except VogeAuthError as err:
            raise ConfigEntryAuthFailed("VOGE token is no longer valid") from err
        except VogeApiError:
            diagnosis_status = "request_failed"
            _LOGGER.debug("VOGE diagnosis request failed; retaining device-list telemetry")
        else:
            if diagnosis_matches_vehicle(candidate, vehicle):
                diagnosis = candidate
                diagnosis_status = "matched"
            elif candidate is None:
                diagnosis_status = "invalid_response"
                _LOGGER.warning("Ignored an invalid VOGE diagnosis response")
            elif candidate.device_id is None:
                diagnosis_status = "missing_device_id"
                _LOGGER.warning("Ignored VOGE diagnosis data without a vehicle identifier")
            else:
                diagnosis_status = "device_mismatch"
                _LOGGER.warning("Ignored VOGE diagnosis data for a different vehicle")

        coordinates_wgs84 = vehicle.coordinates_gcj02
        if coordinates_wgs84 is not None and self.convert_coordinates:
            coordinates_wgs84 = gcj02_to_wgs84(*coordinates_wgs84)

        return TelemetryData(
            vehicle=vehicle,
            diagnosis=diagnosis,
            coordinates_wgs84=coordinates_wgs84,
            fetched_at=datetime.now(UTC),
            bound_vehicle_count=len(vehicles),
            diagnosis_status=diagnosis_status,
        )


class VogeStatisticsCoordinator(DataUpdateCoordinator[StatisticsData]):
    """Fetch the explicit-device current-month summary at a slower interval."""

    def __init__(
        self,
        hass: Any,
        entry: ConfigEntry,
        client: VogeModernClient,
        device_id: str,
        *,
        interval_seconds: int,
        server_timezone: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"voge_statistics_{entry.entry_id}",
            update_interval=timedelta(seconds=interval_seconds),
        )
        self.client = client
        self.device_id = device_id
        self.server_timezone = server_timezone

    async def _async_update_data(self) -> StatisticsData:
        try:
            timezone = ZoneInfo(self.server_timezone)
        except ZoneInfoNotFoundError as err:
            raise UpdateFailed("Invalid configured server timezone") from err
        month = datetime.now(timezone).strftime("%Y-%m")

        try:
            summary = parse_month_summary(await self.client.get_month_index(self.device_id))
        except VogeAuthError as err:
            raise ConfigEntryAuthFailed("VOGE token is no longer valid") from err
        except VogeApiError as err:
            raise UpdateFailed(str(err)) from err

        if summary is not None and summary.device_id not in {None, self.device_id}:
            raise UpdateFailed("Ignored current-month data for a different vehicle")
        return StatisticsData(summary=summary, month=month, fetched_at=datetime.now(UTC))


class VogeAlertCoordinator(DataUpdateCoordinator[AlertData]):
    """Poll read-only vehicle-message history without changing read status."""

    def __init__(
        self,
        hass: Any,
        entry: ConfigEntry,
        client: VogeLegacyClient,
        store: AlertDedupStore,
        *,
        interval_seconds: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"voge_alerts_{entry.entry_id}",
            update_interval=timedelta(seconds=interval_seconds),
        )
        self.client = client
        self.store = store

    async def _async_update_data(self) -> AlertData:
        page_num = 1
        new_messages: list[AlertMessage] = []
        new_ids: set[str] = set()
        server_pages: int | None = None
        server_total: int | None = None
        encountered_known = False
        last_page_size = 0

        while page_num <= ALERT_MAX_PAGES:
            try:
                page = await self.client.get_vehicle_messages(page_num, ALERT_PAGE_SIZE)
            except VogeAuthError as err:
                raise ConfigEntryAuthFailed("VOGE token is no longer valid") from err
            except VogeApiError as err:
                raise UpdateFailed(str(err)) from err

            if not isinstance(page, dict):
                raise UpdateFailed("legacy.messages; invalid_page_response")

            if page_num == 1:
                server_pages = parse_int(page.get("pages"))
                server_total = parse_int(page.get("total"))

            records = page.get("records")
            last_page_size = len(records) if isinstance(records, list) else 0
            messages = parse_alert_messages(records)

            for message in messages:
                if self.store.is_seen(message.stable_id):
                    encountered_known = True
                    continue
                if message.stable_id in new_ids:
                    continue
                new_ids.add(message.stable_id)
                new_messages.append(message)

            if encountered_known or not messages:
                break
            if server_pages is not None and page_num >= server_pages:
                break
            if server_pages is None and last_page_size < ALERT_PAGE_SIZE:
                break
            if page_num >= ALERT_MAX_PAGES:
                break
            page_num += 1

        truncated = (
            not encountered_known
            and page_num >= ALERT_MAX_PAGES
            and last_page_size >= ALERT_PAGE_SIZE
            and (server_pages is None or server_pages > ALERT_MAX_PAGES)
        )
        if truncated:
            _LOGGER.warning(
                "VOGE alert scan reached its page limit; older new messages may remain pending"
            )

        if not self.store.initialized:
            await self.store.async_initialize(list(new_ids))
            new_messages = []
        else:
            new_messages.sort(key=lambda message: (message.create_time or "", message.stable_id))
            self.store.mark_inflight([message.stable_id for message in new_messages])
        return AlertData(
            messages=tuple(new_messages),
            fetched_at=datetime.now(UTC),
            page_scan_truncated=truncated,
            server_pages=server_pages,
            server_total=server_total,
        )
