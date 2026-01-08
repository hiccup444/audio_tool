"""dB and linear amplitude conversion utilities."""

import math


def db_to_linear(db: float) -> float:
    """Convert decibels to linear amplitude.

    Args:
        db: Value in decibels

    Returns:
        Linear amplitude (e.g., 0 dB = 1.0, -6 dB ≈ 0.5, +6 dB ≈ 2.0)
    """
    return 10 ** (db / 20)


def linear_to_db(linear: float) -> float:
    """Convert linear amplitude to decibels.

    Args:
        linear: Linear amplitude value (must be > 0)

    Returns:
        Value in decibels

    Raises:
        ValueError: If linear is <= 0
    """
    if linear <= 0:
        raise ValueError("Linear amplitude must be greater than 0")
    return 20 * math.log10(linear)


def dbfs_to_linear(dbfs: float) -> float:
    """Convert dBFS (decibels relative to full scale) to linear.

    In audio, 0 dBFS = 1.0 (full scale), negative values are quieter.

    Args:
        dbfs: Value in dBFS

    Returns:
        Linear amplitude (0 dBFS = 1.0, -0.3 dBFS ≈ 0.966)
    """
    return db_to_linear(dbfs)


def calculate_gain_for_target(current_lufs: float, target_lufs: float) -> float:
    """Calculate the gain in dB needed to reach target LUFS.

    Args:
        current_lufs: Current integrated loudness in LUFS
        target_lufs: Target integrated loudness in LUFS

    Returns:
        Gain in dB (positive = boost, negative = cut)
    """
    return target_lufs - current_lufs
