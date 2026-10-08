#!/usr/bin/env python3
"""Canonical Bitcoin Core maths, with no external dependencies."""

DIFF1_TARGET = 0x00000000FFFF0000000000000000000000000000000000000000000000000000


def bits_to_target(bits_hex: str) -> int:
    """Decodes the 'bits' field (compact target) into a 256-bit target.

    bits_hex: 8-character hex string, e.g. '170355aa'.
    Returns a Python int (the target).
    """
    if not bits_hex or len(bits_hex) != 8:
        raise ValueError(f"invalid bits: {bits_hex!r}")
    n = int(bits_hex, 16)
    exponent = n >> 24
    mantissa = n & 0x007FFFFF
    if exponent <= 3:
        target = mantissa >> (8 * (3 - exponent))
    else:
        target = mantissa << (8 * (exponent - 3))
    return target


def bits_to_difficulty(bits_hex: str) -> float:
    """Derives difficulty from bits using Core's definition.

    difficulty = DIFF1_TARGET / target

    Returns a float64. It agrees with the 'difficulty' field of Bitcoin Core to
    within 1 ULP, but the type is deterministic (always float).
    """
    target = bits_to_target(bits_hex)
    if target == 0:
        return 0.0
    return DIFF1_TARGET / target


def target_to_bits(target: int) -> str:
    """Encodes a target into 'bits' (compact target)."""
    if target <= 0:
        raise ValueError("target must be positive")
    hex_str = f"{target:x}"
    if len(hex_str) % 2:
        hex_str = "0" + hex_str
    size = len(hex_str) // 2
    if size <= 3:
        compact = target << (8 * (3 - size))
    else:
        compact = target >> (8 * (size - 3))
    if compact & 0x00800000:
        compact >>= 8
        size += 1
    compact |= size << 24
    return f"{compact:08x}"

def difficulty_core(bits_hex: str) -> float:
    """EXACT Bitcoin Core difficulty (GetDifficulty), bit for bit.

    Core does NOT divide DIFF1_TARGET/target: it computes dDiff = 0x0000ffff / mantissa and
    scales it with powers of 256. That is mathematically equivalent, but it differs by ~1 ULP
    from the target method, and OBM publishes Core's double.
    """
    n = int(bits_hex, 16)
    n_shift = (n >> 24) & 0xFF
    d = float(0x0000FFFF) / float(n & 0x00FFFFFF)
    while n_shift < 29:
        d *= 256.0
        n_shift += 1
    while n_shift > 29:
        d /= 256.0
        n_shift -= 1
    return d
