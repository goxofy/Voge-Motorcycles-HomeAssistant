"""SM3 and exact legacy canonicalization tests."""

from custom_components.voge.auth import (
    LegacyApplicationCredentials,
    build_legacy_headers,
    build_legacy_signature,
)
from custom_components.voge.sm3 import sm3_hexdigest


def test_sm3_known_vector() -> None:
    assert sm3_hexdigest(b"abc") == (
        "66c7f0f462eeedd9d1f2d46bdc10e4e2"
        "4167c4875cf2f7a2297da02b8f4ba8e0"
    )


def test_legacy_signature_sorts_and_has_no_delimiters() -> None:
    credentials = LegacyApplicationCredentials("access", "secret")
    timestamp = 1_700_000_000_123
    nonce = "00000000-0000-0000-0000-000000000001"
    expected_text = (
        "accessKey=access"
        "nonce=00000000-0000-0000-0000-000000000001"
        "timestamp=1700000000123"
        "secret"
    )
    assert build_legacy_signature(
        credentials,
        timestamp_ms=timestamp,
        nonce=nonce,
    ) == sm3_hexdigest(expected_text.encode())


def test_legacy_headers_are_lowercase_hex() -> None:
    headers = build_legacy_headers(
        LegacyApplicationCredentials("access", "secret"),
        "token",
        timestamp_ms=123,
        nonce="a-b-c",
    )
    assert headers["Authorization"] == "token"
    assert headers["timestamp"] == "123"
    assert headers["nonce"] == "a-b-c"
    assert len(headers["signature"]) == 64
    assert headers["signature"] == headers["signature"].lower()
