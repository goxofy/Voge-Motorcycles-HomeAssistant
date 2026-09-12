"""Authentication helpers for the VOGE APIs."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from .sm3 import sm3_hexdigest


@dataclass(frozen=True, slots=True)
class LegacyApplicationCredentials:
    """Private credentials required by the legacy service."""

    access_key: str
    signing_secret: str


def load_legacy_application_credentials() -> LegacyApplicationCredentials | None:
    """Load local credentials without exposing them through config or diagnostics."""
    try:
        from ._legacy_credentials import LEGACY_ACCESS_KEY, LEGACY_SIGNING_SECRET
    except ImportError:
        return None

    if not LEGACY_ACCESS_KEY or not LEGACY_SIGNING_SECRET:
        return None
    return LegacyApplicationCredentials(LEGACY_ACCESS_KEY, LEGACY_SIGNING_SECRET)


def build_legacy_signature(
    credentials: LegacyApplicationCredentials,
    *,
    timestamp_ms: int,
    nonce: str,
) -> str:
    """Build the lowercase SM3 signature required by the legacy service."""
    fields = {
        "accessKey": credentials.access_key,
        "timestamp": str(timestamp_ms),
        "nonce": nonce,
    }
    canonical = "".join(
        f"{key}={value}"
        for key, value in sorted(fields.items())
        if value not in (None, "")
    )
    return sm3_hexdigest((canonical + credentials.signing_secret).encode("utf-8"))


def build_legacy_headers(
    credentials: LegacyApplicationCredentials,
    token: str,
    *,
    timestamp_ms: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Build legacy read-only request headers."""
    timestamp_ms = timestamp_ms if timestamp_ms is not None else time.time_ns() // 1_000_000
    nonce = nonce if nonce is not None else str(uuid.uuid4())
    return {
        "accessKey": credentials.access_key,
        "timestamp": str(timestamp_ms),
        "nonce": nonce,
        "signature": build_legacy_signature(
            credentials,
            timestamp_ms=timestamp_ms,
            nonce=nonce,
        ),
        "Authorization": token,
    }
