"""Small dependency-free SM3 implementation."""

from __future__ import annotations

from collections.abc import Iterable

_MASK = 0xFFFFFFFF
_IV = (
    0x7380166F,
    0x4914B2B9,
    0x172442D7,
    0xDA8A0600,
    0xA96F30BC,
    0x163138AA,
    0xE38DEE4D,
    0xB0FB0E4E,
)


def _rotate_left(value: int, bits: int) -> int:
    bits %= 32
    return ((value << bits) | (value >> (32 - bits))) & _MASK


def _p0(value: int) -> int:
    return value ^ _rotate_left(value, 9) ^ _rotate_left(value, 17)


def _p1(value: int) -> int:
    return value ^ _rotate_left(value, 15) ^ _rotate_left(value, 23)


def _ff(x: int, y: int, z: int, index: int) -> int:
    if index <= 15:
        return x ^ y ^ z
    return (x & y) | (x & z) | (y & z)


def _gg(x: int, y: int, z: int, index: int) -> int:
    if index <= 15:
        return x ^ y ^ z
    return (x & y) | ((~x) & z)


def _pad(data: bytes) -> bytes:
    bit_length = len(data) * 8
    padded = bytearray(data)
    padded.append(0x80)
    while len(padded) % 64 != 56:
        padded.append(0)
    padded.extend(bit_length.to_bytes(8, "big"))
    return bytes(padded)


def _blocks(data: bytes) -> Iterable[bytes]:
    for offset in range(0, len(data), 64):
        yield data[offset : offset + 64]


def sm3_digest(data: bytes) -> bytes:
    """Return the 32-byte SM3 digest for data."""
    state = list(_IV)

    for block in _blocks(_pad(data)):
        words = [int.from_bytes(block[index : index + 4], "big") for index in range(0, 64, 4)]
        words.extend([0] * 52)
        for index in range(16, 68):
            words[index] = (
                _p1(words[index - 16] ^ words[index - 9] ^ _rotate_left(words[index - 3], 15))
                ^ _rotate_left(words[index - 13], 7)
                ^ words[index - 6]
            ) & _MASK
        expanded = [words[index] ^ words[index + 4] for index in range(64)]

        a, b, c, d, e, f, g, h = state
        for index in range(64):
            constant = 0x79CC4519 if index <= 15 else 0x7A879D8A
            ss1 = _rotate_left(
                (_rotate_left(a, 12) + e + _rotate_left(constant, index)) & _MASK,
                7,
            )
            ss2 = ss1 ^ _rotate_left(a, 12)
            tt1 = (_ff(a, b, c, index) + d + ss2 + expanded[index]) & _MASK
            tt2 = (_gg(e, f, g, index) + h + ss1 + words[index]) & _MASK
            d = c
            c = _rotate_left(b, 9)
            b = a
            a = tt1
            h = g
            g = _rotate_left(f, 19)
            f = e
            e = _p0(tt2)

        state = [
            state[0] ^ a,
            state[1] ^ b,
            state[2] ^ c,
            state[3] ^ d,
            state[4] ^ e,
            state[5] ^ f,
            state[6] ^ g,
            state[7] ^ h,
        ]

    return b"".join(value.to_bytes(4, "big") for value in state)


def sm3_hexdigest(data: bytes) -> str:
    """Return a lowercase hexadecimal SM3 digest."""
    return sm3_digest(data).hex()
