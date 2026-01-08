"""FFmpeg subprocess utilities."""

import subprocess
import shutil
from typing import Optional


def check_ffmpeg() -> bool:
    """Check if FFmpeg is available in PATH.

    Returns:
        True if FFmpeg is available, False otherwise
    """
    return shutil.which("ffmpeg") is not None


def get_ffmpeg_path() -> str:
    """Get the path to FFmpeg executable.

    Returns:
        Path to FFmpeg executable

    Raises:
        RuntimeError: If FFmpeg is not found
    """
    path = shutil.which("ffmpeg")
    if path is None:
        raise RuntimeError(
            "FFmpeg not found. Please install FFmpeg and ensure it's in your PATH.\n"
            "Download from: https://ffmpeg.org/download.html"
        )
    return path


def run_ffmpeg(
    args: list[str],
    input_data: Optional[bytes] = None,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess:
    """Run FFmpeg with the given arguments.

    Args:
        args: List of arguments to pass to FFmpeg (excluding 'ffmpeg' itself)
        input_data: Optional bytes to pipe to FFmpeg's stdin
        timeout: Optional timeout in seconds

    Returns:
        CompletedProcess with stdout, stderr, and return code

    Raises:
        RuntimeError: If FFmpeg is not found
        subprocess.TimeoutExpired: If the command times out
        subprocess.CalledProcessError: If FFmpeg returns non-zero exit code
    """
    ffmpeg_path = get_ffmpeg_path()

    cmd = [ffmpeg_path] + args

    result = subprocess.run(
        cmd,
        input=input_data,
        capture_output=True,
        timeout=timeout,
    )

    return result


def run_ffmpeg_analysis(
    input_path: str,
    audio_filter: str,
    timeout: Optional[float] = 300,
) -> str:
    """Run FFmpeg with an audio filter for analysis (output to null).

    Args:
        input_path: Path to input audio file
        audio_filter: FFmpeg audio filter string (e.g., 'ebur128', 'loudnorm')
        timeout: Timeout in seconds (default 5 minutes)

    Returns:
        FFmpeg's stderr output (where analysis results are printed)

    Raises:
        RuntimeError: If FFmpeg fails or is not found
    """
    args = [
        "-i", input_path,
        "-af", audio_filter,
        "-f", "null",
        "-"
    ]

    result = run_ffmpeg(args, timeout=timeout)

    # FFmpeg prints analysis to stderr
    return result.stderr.decode("utf-8", errors="replace")


def run_ffmpeg_analysis_from_pipe(
    audio_data: bytes,
    sample_rate: int,
    channels: int,
    audio_filter: str,
    timeout: Optional[float] = 300,
) -> str:
    """Run FFmpeg analysis on audio data from memory.

    Args:
        audio_data: Raw PCM audio data as bytes (float32, little-endian)
        sample_rate: Sample rate of the audio
        channels: Number of channels
        audio_filter: FFmpeg audio filter string
        timeout: Timeout in seconds

    Returns:
        FFmpeg's stderr output
    """
    args = [
        "-f", "f32le",  # 32-bit float, little-endian
        "-ar", str(sample_rate),
        "-ac", str(channels),
        "-i", "pipe:0",
        "-af", audio_filter,
        "-f", "null",
        "-"
    ]

    result = run_ffmpeg(args, input_data=audio_data, timeout=timeout)

    return result.stderr.decode("utf-8", errors="replace")
