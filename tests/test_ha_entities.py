"""Home Assistant entity behavior tests that never call the network."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

pytest.importorskip("homeassistant")

from custom_components.voge.const import DOMAIN, EVENT_VEHICLE_ALERT
from custom_components.voge.coordinator import (
    AlertData,
    TelemetryData,
    VogeAlertCoordinator,
)
from custom_components.voge.device_tracker import VogeDeviceTracker
from custom_components.voge.event import VogeAlertEvent
from custom_components.voge.models import (
    parse_alert_message,
    parse_diagnosis,
    parse_vehicle,
)
from custom_components.voge.runtime import VogeRuntimeData
from custom_components.voge.sensor import (
    SENSORS,
    STATISTICS_SENSORS,
    VogeSensor,
    VogeStatisticsSensor,
)


class _AlertStore:
    def __init__(self) -> None:
        self.initialized = True
        self.acknowledged: list[str] = []
        self.released: list[str] = []
        self.inflight: list[str] = []

    def is_seen(self, message_id: str) -> bool:
        return message_id in self.acknowledged or message_id in self.inflight

    def mark_inflight(self, message_ids: list[str]) -> None:
        self.inflight.extend(message_ids)

    async def async_initialize(self, message_ids: list[str]) -> None:
        self.initialized = True
        self.acknowledged.extend(message_ids)

    async def async_acknowledge(self, message_ids: list[str]) -> None:
        self.acknowledged.extend(message_ids)

    def release_inflight(self, message_ids: list[str]) -> None:
        self.released.extend(message_ids)
        self.inflight = [message_id for message_id in self.inflight if message_id not in message_ids]


class _EventBus:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[tuple[str, dict[str, Any]]] = []

    def async_fire(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.fail:
            raise RuntimeError("synthetic bus failure")
        self.events.append((event_type, payload))


class _FakeHass:
    def __init__(self, *, fail_bus: bool = False) -> None:
        self.bus = _EventBus(fail=fail_bus)
        self.tasks: list[asyncio.Task[Any]] = []

    def async_create_task(
        self,
        target: Coroutine[Any, Any, Any],
        name: str,
    ) -> asyncio.Task[Any]:
        task = asyncio.create_task(target, name=name)
        self.tasks.append(task)
        return task


class _AlertClient:
    def __init__(self, records_per_page: int) -> None:
        self.records_per_page = records_per_page
        self.calls: list[int] = []

    async def get_vehicle_messages(self, page_num: int, page_size: int) -> dict[str, Any]:
        self.calls.append(page_num)
        return {
            "records": [
                {
                    "messageId": f"message-{page_num}-{index}",
                    "module": 1,
                    "type": 3,
                    "title": "Synthetic vibration",
                    "content": "Synthetic content",
                }
                for index in range(min(self.records_per_page, page_size))
            ]
        }


def _telemetry_data(*, bound_vehicle_count: int = 1) -> TelemetryData:
    vehicle = parse_vehicle(
        {
            "deviceId": "synthetic-device",
            "productName": "Synthetic CU250",
            "geoLatitude": "29.56",
            "geoLongitude": "106.55",
        }
    )
    assert vehicle is not None
    return TelemetryData(
        vehicle=vehicle,
        diagnosis=None,
        coordinates_wgs84=(29.557, 106.546),
        fetched_at=datetime(2026, 9, 11, tzinfo=UTC),
        bound_vehicle_count=bound_vehicle_count,
        diagnosis_status="matched",
    )


def _runtime(*, bound_vehicle_count: int = 1) -> tuple[VogeRuntimeData, _AlertStore]:
    telemetry = SimpleNamespace(
        data=_telemetry_data(bound_vehicle_count=bound_vehicle_count),
        last_update_success=False,
    )
    message = parse_alert_message(
        {
            "messageId": "synthetic-message",
            "module": 1,
            "type": 3,
            "title": "Synthetic vibration",
            "content": "Synthetic content",
            "createTime": "2026-09-11 12:00:00",
            "ifRead": 0,
        }
    )
    assert message is not None
    store = _AlertStore()
    alerts = SimpleNamespace(
        data=AlertData(
            messages=(message,),
            fetched_at=datetime(2026, 9, 11, tzinfo=UTC),
            page_scan_truncated=False,
            server_pages=1,
            server_total=1,
        ),
        last_update_success=True,
        store=store,
    )
    runtime = cast(
        VogeRuntimeData,
        SimpleNamespace(
            telemetry=telemetry,
            statistics=SimpleNamespace(data=None, last_update_success=True),
            alerts=alerts,
            device_key="device-key",
            account_key="account-key",
            product_name="Synthetic CU250",
            product_id="synthetic-product",
            convert_coordinates=True,
        ),
    )
    return runtime, store


def test_tracker_keeps_last_location_after_update_failure() -> None:
    """A failed refresh must not erase the coordinator's last valid coordinates."""
    runtime, _ = _runtime()
    tracker = VogeDeviceTracker(runtime)

    assert runtime.telemetry.last_update_success is False
    assert tracker.available is True
    assert tracker.latitude == 29.557
    assert tracker.longitude == 106.546

    cast(Any, runtime.telemetry).data = None
    assert tracker.available is False


def test_vehicle_device_info_is_consistent_and_never_duplicates_brand() -> None:
    """All vehicle coordinators attach to one conservatively named device."""
    runtime, _ = _runtime()
    vehicle = parse_vehicle(
        {
            "deviceId": "synthetic-device",
            "deviceName": "VOGE product 2",
            "productId": "2",
        }
    )
    assert vehicle is not None
    cast(Any, runtime.telemetry).data = TelemetryData(
        vehicle=vehicle,
        diagnosis=None,
        coordinates_wgs84=None,
        fetched_at=datetime(2026, 9, 12, tzinfo=UTC),
        bound_vehicle_count=1,
        diagnosis_status="matched",
    )
    runtime.product_name = "Saved fallback"

    tracker = VogeDeviceTracker(runtime)
    statistics = VogeStatisticsSensor(runtime, STATISTICS_SENSORS[0])
    tracker_info = tracker.device_info
    statistics_info = statistics.device_info

    assert tracker_info == statistics_info
    assert tracker_info.get("name") == "VOGE product 2"
    assert tracker_info.get("model") == "VOGE product 2"
    assert "model_id" not in tracker_info


def test_diagnosis_menu_precedes_vehicle_menu_for_capability_state() -> None:
    """M2 can explicitly override M1 without involving the static model catalog."""
    runtime, _ = _runtime()
    cast(Any, runtime.telemetry).last_update_success = True
    vehicle = parse_vehicle(
        {
            "deviceId": "synthetic-device",
            "productName": "Synthetic CU250",
            "menu": {"voltage": 1},
        }
    )
    unsupported = parse_diagnosis(
        {"deviceId": "synthetic-device", "menu": {"voltage": 0}}
    )
    supported = parse_diagnosis(
        {"deviceId": "synthetic-device", "menu": {"voltage": 1}}
    )
    assert vehicle is not None
    assert unsupported is not None
    assert supported is not None
    description = next(item for item in SENSORS if item.key == "voltage")
    sensor = VogeSensor(runtime, description)

    cast(Any, runtime.telemetry).data = TelemetryData(
        vehicle=vehicle,
        diagnosis=unsupported,
        coordinates_wgs84=None,
        fetched_at=datetime(2026, 9, 12, tzinfo=UTC),
        bound_vehicle_count=1,
        diagnosis_status="matched",
    )
    assert sensor.available is False

    cast(Any, runtime.telemetry).data = TelemetryData(
        vehicle=vehicle,
        diagnosis=supported,
        coordinates_wgs84=None,
        fetched_at=datetime(2026, 9, 12, tzinfo=UTC),
        bound_vehicle_count=1,
        diagnosis_status="matched",
    )
    assert sensor.available is True
    assert sensor.native_value is None

    cast(Any, runtime.telemetry).last_update_success = False
    assert sensor.available is False


def test_default_enabled_sensor_uses_value_when_capability_menu_is_stale() -> None:
    """A stale M2 capability flag must not hide a valid default-enabled value."""
    runtime, _ = _runtime()
    cast(Any, runtime.telemetry).last_update_success = True
    vehicle = parse_vehicle(
        {
            "deviceId": "synthetic-device",
            "productName": "Synthetic CU250",
            "sumDistance": 122,
            "menu": {"sumDistance": 1},
        }
    )
    diagnosis = parse_diagnosis(
        {
            "deviceId": "synthetic-device",
            "sumDistance": 122,
            "menu": {"sumDistance": 0},
        }
    )
    assert vehicle is not None
    assert diagnosis is not None
    description = next(item for item in SENSORS if item.key == "total_mileage")
    sensor = VogeSensor(runtime, description)

    cast(Any, runtime.telemetry).data = TelemetryData(
        vehicle=vehicle,
        diagnosis=diagnosis,
        coordinates_wgs84=None,
        fetched_at=datetime(2026, 9, 12, tzinfo=UTC),
        bound_vehicle_count=1,
        diagnosis_status="matched",
    )

    assert sensor.native_value == 122
    assert sensor.available is True


def test_unknown_capability_requires_a_valid_value() -> None:
    """An absent menu flag never invents support from a model-catalog match."""
    runtime, _ = _runtime()
    cast(Any, runtime.telemetry).last_update_success = True
    vehicle = parse_vehicle(
        {
            "deviceId": "synthetic-device",
            "deviceName": "CU250 II代自动挡",
        }
    )
    empty_diagnosis = parse_diagnosis({"deviceId": "synthetic-device"})
    valued_diagnosis = parse_diagnosis(
        {"deviceId": "synthetic-device", "voltage": "12.6"}
    )
    assert vehicle is not None
    assert empty_diagnosis is not None
    assert valued_diagnosis is not None
    description = next(item for item in SENSORS if item.key == "voltage")
    sensor = VogeSensor(runtime, description)

    cast(Any, runtime.telemetry).data = TelemetryData(
        vehicle=vehicle,
        diagnosis=empty_diagnosis,
        coordinates_wgs84=None,
        fetched_at=datetime(2026, 9, 12, tzinfo=UTC),
        bound_vehicle_count=1,
        diagnosis_status="matched",
    )
    assert sensor.available is False

    cast(Any, runtime.telemetry).data = TelemetryData(
        vehicle=vehicle,
        diagnosis=valued_diagnosis,
        coordinates_wgs84=None,
        fetched_at=datetime(2026, 9, 12, tzinfo=UTC),
        bound_vehicle_count=1,
        diagnosis_status="matched",
    )
    assert sensor.available is True
    assert sensor.native_value == 12.6


def test_alert_is_account_scoped_and_acknowledged_after_delivery() -> None:
    """A delivered account message is emitted once and then acknowledged locally."""

    async def scenario() -> None:
        runtime, store = _runtime(bound_vehicle_count=1)
        hass = _FakeHass()
        entity = VogeAlertEvent(runtime)
        cast(Any, entity).hass = hass
        cast(Any, entity).async_write_ha_state = Mock()

        entity._handle_coordinator_update()
        await asyncio.gather(*hass.tasks)

        assert entity.device_info.get("identifiers") == {(DOMAIN, "account_account-key")}
        assert store.acknowledged == ["synthetic-message"]
        assert store.released == []
        assert hass.bus.events == [
            (
                EVENT_VEHICLE_ALERT,
                {
                    "message_id": "synthetic-message",
                    "module": 1,
                    "raw_type": 3,
                    "event_type": "vibration",
                    "mapping_confidence": "confirmed_static",
                    "title": "Synthetic vibration",
                    "content": "Synthetic content",
                    "content_plain": "Synthetic content",
                    "create_time": "2026-09-11 12:00:00",
                    "param": None,
                    "if_read": 0,
                    "vehicle_attribution": "single_vehicle_assumption",
                },
            )
        ]

    asyncio.run(scenario())


def test_alert_delivery_failure_releases_inflight_id() -> None:
    """A failed event-bus delivery must remain eligible for the next poll."""
    runtime, store = _runtime(bound_vehicle_count=2)
    hass = _FakeHass(fail_bus=True)
    entity = VogeAlertEvent(runtime)
    cast(Any, entity).hass = hass
    cast(Any, entity).async_write_ha_state = Mock()

    with pytest.raises(RuntimeError, match="synthetic bus failure"):
        entity._handle_coordinator_update()

    assert store.acknowledged == []
    assert store.released == ["synthetic-message"]


def test_alert_scan_reports_unknown_page_count_truncation() -> None:
    """Five full pages without metadata must not be treated as complete."""

    async def scenario() -> None:
        client = _AlertClient(records_per_page=50)
        store = _AlertStore()
        coordinator = cast(Any, object.__new__(VogeAlertCoordinator))
        coordinator.client = client
        coordinator.store = store

        result = await coordinator._async_update_data()

        assert client.calls == [1, 2, 3, 4, 5]
        assert len(result.messages) == 250
        assert result.page_scan_truncated is True
        assert result.server_pages is None

    asyncio.run(scenario())


def test_alert_scan_stops_on_short_page_without_metadata() -> None:
    """A short page is a safe completion signal when page metadata is absent."""

    async def scenario() -> None:
        client = _AlertClient(records_per_page=10)
        store = _AlertStore()
        coordinator = cast(Any, object.__new__(VogeAlertCoordinator))
        coordinator.client = client
        coordinator.store = store

        result = await coordinator._async_update_data()

        assert client.calls == [1]
        assert len(result.messages) == 10
        assert result.page_scan_truncated is False

    asyncio.run(scenario())
