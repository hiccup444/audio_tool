"""Data models for audio files and loudness measurements."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class LoudnessStats:
    """EBU R128 loudness measurements."""

    integrated_lufs: float
    """Integrated loudness (overall) in LUFS."""

    max_momentary_lufs: float
    """Maximum momentary loudness (400ms window) in LUFS."""

    max_short_term_lufs: float
    """Maximum short-term loudness (3s window) in LUFS."""

    true_peak_dbtp: float
    """True peak level in dBTP."""

    def __str__(self) -> str:
        return (
            f"Integrated: {self.integrated_lufs:.1f} LUFS | "
            f"Max M: {self.max_momentary_lufs:.1f} LUFS | "
            f"Max S: {self.max_short_term_lufs:.1f} LUFS | "
            f"TP: {self.true_peak_dbtp:.1f} dBTP"
        )


@dataclass
class FileProcessingConfig:
    """Configuration for processing a single file."""

    path: Path
    """Path to the audio file."""

    gain_db: Optional[float] = None
    """Manual gain adjustment in dB (±12 dB range)."""

    target_lufs: Optional[float] = None
    """Target integrated loudness in LUFS (auto-calculates gain)."""

    def __post_init__(self):
        if self.gain_db is not None and self.target_lufs is not None:
            raise ValueError("Cannot specify both gain_db and target_lufs")

    @property
    def has_adjustment(self) -> bool:
        """Check if any adjustment is configured."""
        return self.gain_db is not None or self.target_lufs is not None


@dataclass
class AudioFile:
    """Represents an audio file with its metadata and processing state."""

    path: Path
    """Path to the audio file."""

    sample_rate: int
    """Sample rate in Hz."""

    channels: int
    """Number of audio channels."""

    duration_seconds: float
    """Duration in seconds."""

    data: Optional[np.ndarray] = field(default=None, repr=False)
    """Audio data as numpy array (float32, shape: samples x channels)."""

    original_loudness: Optional[LoudnessStats] = None
    """Loudness measurements of the original file."""

    processed_loudness: Optional[LoudnessStats] = None
    """Loudness measurements after processing."""

    gain_applied_db: float = 0.0
    """Gain that was applied in dB."""

    hard_clip_applied: bool = False
    """Whether hard clipping was applied."""

    @property
    def is_loaded(self) -> bool:
        """Check if audio data is loaded in memory."""
        return self.data is not None

    @property
    def filename(self) -> str:
        """Get just the filename."""
        return self.path.name

    @classmethod
    def from_file(cls, path: Path) -> "AudioFile":
        """Create an AudioFile by loading from disk.

        Args:
            path: Path to the audio file

        Returns:
            AudioFile with data loaded
        """
        import soundfile as sf

        data, sample_rate = sf.read(str(path), dtype="float32")

        # Ensure 2D array (samples x channels)
        if data.ndim == 1:
            data = data.reshape(-1, 1)

        channels = data.shape[1]
        duration = len(data) / sample_rate

        return cls(
            path=path,
            sample_rate=sample_rate,
            channels=channels,
            duration_seconds=duration,
            data=data,
        )

    def get_data_bytes(self) -> bytes:
        """Get audio data as raw bytes (float32, little-endian).

        Returns:
            Raw PCM bytes suitable for piping to FFmpeg
        """
        if self.data is None:
            raise ValueError("Audio data not loaded")
        return self.data.astype("<f4").tobytes()
