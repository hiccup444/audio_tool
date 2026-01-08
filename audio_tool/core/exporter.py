"""Audio export functionality using FFmpeg."""

import subprocess
from pathlib import Path
from typing import Literal, Optional

import numpy as np
import soundfile as sf

from audio_tool.config import FFMPEG_CODECS, DEFAULT_QUALITY
from audio_tool.utils.ffmpeg import get_ffmpeg_path

OutputFormat = Literal["wav", "ogg", "flac", "mp3"]


class AudioExporter:
    """Export audio to various formats using FFmpeg."""

    def __init__(self):
        self.ffmpeg_path = get_ffmpeg_path()

    def export(
        self,
        audio: np.ndarray,
        sample_rate: int,
        output_path: Path,
        format: OutputFormat,
        quality: Optional[str] = None,
    ) -> Path:
        """Export audio array to file in specified format.

        Args:
            audio: Audio data as numpy array (float32)
            sample_rate: Sample rate in Hz
            output_path: Output file path (extension will be adjusted)
            format: Output format ('wav', 'ogg', 'flac', 'mp3')
            quality: Format-specific quality setting (optional)

        Returns:
            Path to the exported file
        """
        # Ensure correct extension
        extensions = {
            "wav": ".wav",
            "ogg": ".ogg",
            "flac": ".flac",
            "mp3": ".mp3",
        }
        output_file = output_path.with_suffix(extensions[format])

        # Ensure output directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # For WAV, we can use soundfile directly (more reliable)
        if format == "wav":
            return self._export_wav(audio, sample_rate, output_file)

        # For other formats, use FFmpeg
        return self._export_via_ffmpeg(
            audio, sample_rate, output_file, format, quality
        )

    def _export_wav(
        self,
        audio: np.ndarray,
        sample_rate: int,
        output_path: Path,
    ) -> Path:
        """Export to WAV using soundfile.

        Args:
            audio: Audio data
            sample_rate: Sample rate
            output_path: Output path

        Returns:
            Path to exported file
        """
        # Use 16-bit PCM for compatibility
        sf.write(str(output_path), audio, sample_rate, subtype="PCM_16")
        return output_path

    def _export_via_ffmpeg(
        self,
        audio: np.ndarray,
        sample_rate: int,
        output_path: Path,
        format: OutputFormat,
        quality: Optional[str] = None,
    ) -> Path:
        """Export to OGG/FLAC/MP3 via FFmpeg.

        Args:
            audio: Audio data (float32)
            sample_rate: Sample rate
            output_path: Output path
            format: Output format
            quality: Optional quality setting

        Returns:
            Path to exported file
        """
        codec = FFMPEG_CODECS[format]
        quality = quality or DEFAULT_QUALITY.get(format)

        # Ensure 2D array
        if audio.ndim == 1:
            audio = audio.reshape(-1, 1)

        channels = audio.shape[1]

        # Build FFmpeg command
        cmd = [
            self.ffmpeg_path,
            "-y",  # Overwrite output
            "-f", "f32le",  # Input format: 32-bit float, little-endian
            "-ar", str(sample_rate),
            "-ac", str(channels),
            "-i", "pipe:0",  # Read from stdin
            "-c:a", codec,
        ]

        # Add format-specific quality options
        if format == "mp3" and quality:
            cmd.extend(["-b:a", quality])
        elif format == "ogg" and quality:
            cmd.extend(["-q:a", quality])
        elif format == "flac" and quality:
            cmd.extend(["-compression_level", quality])

        cmd.append(str(output_path))

        # Pipe audio data to FFmpeg
        audio_bytes = audio.astype("<f4").tobytes()

        result = subprocess.run(
            cmd,
            input=audio_bytes,
            capture_output=True,
        )

        if result.returncode != 0:
            error_msg = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"FFmpeg export failed: {error_msg}")

        return output_path

    def export_batch(
        self,
        files: list[tuple[np.ndarray, int, Path]],
        format: OutputFormat,
        quality: Optional[str] = None,
        on_progress: Optional[callable] = None,
    ) -> list[Path]:
        """Export multiple files.

        Args:
            files: List of (audio_data, sample_rate, output_path) tuples
            format: Output format
            quality: Optional quality setting
            on_progress: Optional callback(current, total) for progress

        Returns:
            List of exported file paths
        """
        exported = []
        total = len(files)

        for i, (audio, sample_rate, output_path) in enumerate(files):
            exported_path = self.export(audio, sample_rate, output_path, format, quality)
            exported.append(exported_path)

            if on_progress:
                on_progress(i + 1, total)

        return exported
