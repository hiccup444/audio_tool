"""Audio processing operations: gain adjustment and hard clipping."""

import numpy as np

from audio_tool.config import HARD_CLIP_THRESHOLD_DBFS, MAX_GAIN_DB
from audio_tool.utils.conversion import db_to_linear, calculate_gain_for_target


class AudioProcessor:
    """Audio processing operations for gain and clipping."""

    @staticmethod
    def apply_gain(audio: np.ndarray, gain_db: float) -> np.ndarray:
        """Apply gain adjustment to audio signal.

        Args:
            audio: Audio data as numpy array (float32)
            gain_db: Gain adjustment in dB

        Returns:
            Audio with gain applied

        Raises:
            ValueError: If gain is outside ±12 dB range
        """
        if gain_db < -MAX_GAIN_DB or gain_db > MAX_GAIN_DB:
            raise ValueError(f"Gain must be between -{MAX_GAIN_DB} and +{MAX_GAIN_DB} dB")

        if gain_db == 0.0:
            return audio.copy()

        gain_linear = db_to_linear(gain_db)
        return audio * gain_linear

    @staticmethod
    def hard_clip(
        audio: np.ndarray,
        threshold_dbfs: float = HARD_CLIP_THRESHOLD_DBFS,
    ) -> np.ndarray:
        """Apply hard clipping at the specified threshold.

        Hard clipping simply limits the signal to the threshold value,
        preventing any samples from exceeding it. This is useful for
        preventing inter-sample peaks in lossy codecs.

        Args:
            audio: Audio data as numpy array (float32, range -1.0 to 1.0)
            threshold_dbfs: Clipping threshold in dBFS (default -0.3)

        Returns:
            Clipped audio array
        """
        threshold_linear = db_to_linear(threshold_dbfs)
        return np.clip(audio, -threshold_linear, threshold_linear)

    @staticmethod
    def calculate_gain_for_target_lufs(
        current_lufs: float,
        target_lufs: float,
        clamp_to_max: bool = True,
    ) -> float:
        """Calculate the gain needed to reach target LUFS.

        Args:
            current_lufs: Current integrated loudness in LUFS
            target_lufs: Target integrated loudness in LUFS
            clamp_to_max: If True, clamp gain to ±MAX_GAIN_DB

        Returns:
            Gain in dB (positive = boost, negative = cut)
        """
        gain = calculate_gain_for_target(current_lufs, target_lufs)

        if clamp_to_max:
            gain = max(-MAX_GAIN_DB, min(MAX_GAIN_DB, gain))

        return gain

    @staticmethod
    def process(
        audio: np.ndarray,
        gain_db: float = 0.0,
        apply_hard_clip: bool = False,
        clip_threshold_dbfs: float = HARD_CLIP_THRESHOLD_DBFS,
    ) -> np.ndarray:
        """Apply full processing chain to audio.

        Processing order:
        1. Gain adjustment
        2. Hard clipping (if enabled)

        Args:
            audio: Audio data as numpy array
            gain_db: Gain adjustment in dB (default 0.0)
            apply_hard_clip: Whether to apply hard clipping (default False)
            clip_threshold_dbfs: Clipping threshold in dBFS (default -0.3)

        Returns:
            Processed audio array
        """
        result = audio

        # Apply gain if non-zero
        if gain_db != 0.0:
            result = AudioProcessor.apply_gain(result, gain_db)

        # Apply hard clipping if enabled
        if apply_hard_clip:
            result = AudioProcessor.hard_clip(result, clip_threshold_dbfs)

        return result

    @staticmethod
    def get_peak_dbfs(audio: np.ndarray) -> float:
        """Get the peak level of audio in dBFS.

        Args:
            audio: Audio data as numpy array

        Returns:
            Peak level in dBFS (0 dBFS = full scale)
        """
        peak = np.max(np.abs(audio))
        if peak == 0:
            return float("-inf")
        return 20 * np.log10(peak)

    @staticmethod
    def will_clip(audio: np.ndarray, gain_db: float) -> bool:
        """Check if applying gain will cause clipping (exceed 0 dBFS).

        Args:
            audio: Audio data as numpy array
            gain_db: Proposed gain in dB

        Returns:
            True if audio will clip after gain is applied
        """
        current_peak = np.max(np.abs(audio))
        gain_linear = db_to_linear(gain_db)
        new_peak = current_peak * gain_linear
        return new_peak > 1.0
