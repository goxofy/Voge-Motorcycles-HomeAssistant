"""Minimal persistent alert deduplication state."""

from __future__ import annotations

from collections import deque
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import MAX_RECENT_MESSAGE_IDS, STORE_KEY_PREFIX, STORE_VERSION


class AlertDedupStore:
    """Persist message IDs only; never persist message bodies for deduplication."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORE_VERSION,
            f"{STORE_KEY_PREFIX}.{entry_id}",
        )
        self._recent: deque[str] = deque(maxlen=MAX_RECENT_MESSAGE_IDS)
        self._known: set[str] = set()
        self._inflight: set[str] = set()
        self.initialized = False

    async def async_load(self) -> None:
        """Load bounded IDs from Home Assistant storage."""
        data = await self._store.async_load()
        if not isinstance(data, dict):
            return
        values = data.get("message_ids")
        if isinstance(values, list):
            for value in values[-MAX_RECENT_MESSAGE_IDS:]:
                if isinstance(value, str) and value:
                    self._append(value)
        self.initialized = bool(data.get("initialized"))

    def is_seen(self, message_id: str) -> bool:
        """Return whether an event is persisted or already queued for delivery."""
        return message_id in self._known or message_id in self._inflight

    def mark_inflight(self, message_ids: list[str]) -> None:
        """Prevent duplicate delivery while the event entity acknowledges messages."""
        self._inflight.update(message_ids)

    async def async_initialize(self, message_ids: list[str]) -> None:
        """Establish the first-poll baseline without replaying historical events."""
        for message_id in message_ids:
            self._append(message_id)
        self.initialized = True
        await self._async_save()

    async def async_acknowledge(self, message_ids: list[str]) -> None:
        """Persist IDs after the event entity has fired the corresponding events."""
        for message_id in message_ids:
            self._inflight.discard(message_id)
            self._append(message_id)
        await self._async_save()

    def release_inflight(self, message_ids: list[str]) -> None:
        """Permit redelivery when an event entity could not acknowledge a batch."""
        self._inflight.difference_update(message_ids)

    def _append(self, message_id: str) -> None:
        if message_id in self._known:
            return
        if len(self._recent) == self._recent.maxlen:
            evicted = self._recent[0]
            self._known.discard(evicted)
        self._recent.append(message_id)
        self._known.add(message_id)

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "initialized": self.initialized,
                "message_ids": list(self._recent),
            }
        )
