#!/usr/bin/env python3
"""Matemática canónica de Bitcoin Core, sin dependencias externas."""

DIFF1_TARGET = 0x00000000FFFF0000000000000000000000000000000000000000000000000000


def bits_to_target(bits_hex: str) -> int:
    """Decodifica el campo 'bits' (compact target) a target de 256 bits.

    bits_hex: string hex de 8 caracteres, ej. '170355aa'.
    Devuelve un entero Python (target).
    """
    if not bits_hex or len(bits_hex) != 8:
        raise ValueError(f"bits inválido: {bits_hex!r}")
    n = int(bits_hex, 16)
    exponent = n >> 24
    mantissa = n & 0x007FFFFF
    if exponent <= 3:
        target = mantissa >> (8 * (3 - exponent))
    else:
        target = mantissa << (8 * (exponent - 3))
    return target


def bits_to_difficulty(bits_hex: str) -> float:
    """Deriva difficulty desde bits usando la definición de Core.

    difficulty = DIFF1_TARGET / target

    Devuelve float64. Coincide con el campo 'difficulty' de Bitcoin Core
    dentro de 1 ULP, pero el tipo es determinista (siempre float).
    """
    target = bits_to_target(bits_hex)
    if target == 0:
        return 0.0
    return DIFF1_TARGET / target


def target_to_bits(target: int) -> str:
    """Codifica un target a 'bits' (compact target)."""
    if target <= 0:
        raise ValueError("target debe ser positivo")
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
    """Difficulty EXACTA de Bitcoin Core (GetDifficulty), bit a bit.

    Core NO divide DIFF1_TARGET/target: calcula dDiff = 0x0000ffff / mantissa y lo
    escala con potencias de 256. Es matematicamente equivalente, pero difiere en
    ~1 ULP del metodo del target, y OBM publica el double de Core.
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
