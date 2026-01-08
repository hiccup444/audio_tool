"""EBU R128 loudness measurement using FFmpeg."""

import json
import re
from pathlib import Path
from typing import Optional

from audio_tool.core.audio_file import LoudnessStats
from audio_tool.utils.ffmpeg import run_ffmpeg_analysis, run_ffmpeg_analysis_from_pipe


class LoudnessAnalyzer:
    """Analyze audio loudness using FFmpeg's EBU R128 filters."""

    def analyze_file(self, file_path: Path) -> LoudnessStats:
        """Analyze an audio file and return full EBU R128 stats.

        Args:
            file_path: Path to the audio file

        Returns:
            LoudnessStats with all measurements
        """
        # Run ebur128 filter for momentary/short-term maximums
        ebur128_output = run_ffmpeg_analysis(
            str(file_path),
            "ebur128=framelog=verbose"
        )
        ebur128_stats = self._parse_ebur128_output(ebur128_output)

        # Run loudnorm filter for accurate integrated loudness and true peak
        loudnorm_output = run_ffmpeg_analysis(
            str(file_path),
            "loudnorm=I=-24:TP=-2:LRA=7:print_format=json"
        )
        loudnorm_stats = self._parse_loudnorm_json(loudnorm_output)

        return LoudnessStats(
            integrated_lufs=loudnorm_stats["input_i"],
            max_momentary_lufs=ebur128_stats["max_momentary"],
            max_short_term_lufs=ebur128_stats["max_short_term"],
            true_peak_dbtp=loudnorm_stats["input_tp"],
        )

    def analyze_audio_data(
        self,
        audio_data: bytes,
        sample_rate: int,
        channels: int,
    ) -> LoudnessStats:
        """Analyze audio data from memory.

        Args:
            audio_data: Raw PCM audio data (float32, little-endian)
            sample_rate: Sample rate in Hz
            channels: Number of channels

        Returns:
            LoudnessStats with all measurements
        """
        # Run ebur128 filter
        ebur128_output = run_ffmpeg_analysis_from_pipe(
            audio_data, sample_rate, channels,
            "ebur128=framelog=verbose"
        )
        ebur128_stats = self._parse_ebur128_output(ebur128_output)

        # Run loudnorm filter
        loudnorm_output = run_ffmpeg_analysis_from_pipe(
            audio_data, sample_rate, channels,
            "loudnorm=I=-24:TP=-2:LRA=7:print_format=json"
        )
        loudnorm_stats = self._parse_loudnorm_json(loudnorm_output)

        return LoudnessStats(
            integrated_lufs=loudnorm_stats["input_i"],
            max_momentary_lufs=ebur128_stats["max_momentary"],
            max_short_term_lufs=ebur128_stats["max_short_term"],
            true_peak_dbtp=loudnorm_stats["input_tp"],
        )

    def _parse_ebur128_output(self, stderr: str) -> dict:
        """Parse ebur128 verbose output for max momentary and short-term.

        The ebur128 filter outputs lines like:
        [Parsed_ebur128_0 @ ...] t: 0.4     TARGET:-23 LUFS    M: -22.5 S: -22.8 ...

        We track the maximum M (momentary) and S (short-term) values.

        Args:
            stderr: FFmpeg stderr output

        Returns:
            Dict with 'max_momentary' and 'max_short_term' keys
        """
        max_momentary = float("-inf")
        max_short_term = float("-inf")

        # Pattern to match M: and S: values
        # Example: M: -22.5 S: -22.8
        pattern = re.compile(r"M:\s*([-\d.]+)\s*S:\s*([-\d.]+)")

        for line in stderr.split("\n"):
            match = pattern.search(line)
            if match:
                try:
                    m_val = float(match.group(1))
                    s_val = float(match.group(2))
                    max_momentary = max(max_momentary, m_val)
                    max_short_term = max(max_short_term, s_val)
                except ValueError:
                    continue

        # Also check the summary line for integrated and LRA
        # Summary looks like: I: -23.0 LUFS  LRA: 5.0 LU
        summary_pattern = re.compile(
            r"Summary:.*?I:\s*([-\d.]+)\s*LUFS.*?LRA:\s*([-\d.]+)"
        )

        if max_momentary == float("-inf"):
            # Fallback: try to get from summary or use integrated
            summary_match = summary_pattern.search(stderr)
            if summary_match:
                integrated = float(summary_match.group(1))
                # Use integrated as fallback for both if no frame data
                max_momentary = integrated
                max_short_term = integrated

        return {
            "max_momentary": max_momentary,
            "max_short_term": max_short_term,
        }

    def _parse_loudnorm_json(self, stderr: str) -> dict:
        """Parse loudnorm JSON output.

        The loudnorm filter with print_format=json outputs a JSON block like:
        {
            "input_i" : "-23.00",
            "input_tp" : "-1.00",
            "input_lra" : "5.00",
            ...
        }

        Args:
            stderr: FFmpeg stderr output

        Returns:
            Dict with 'input_i', 'input_tp', 'input_lra' as floats
        """
        # Find the JSON block in stderr
        # It's typically at the end after [Parsed_loudnorm_0 @ ...]
        json_match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.DOTALL)

        if not json_match:
            raise ValueError(
                "Could not find loudnorm JSON output in FFmpeg stderr.\n"
                f"Output was:\n{stderr[:1000]}"
            )

        try:
            data = json.loads(json_match.group())
            return {
                "input_i": float(data["input_i"]),
                "input_tp": float(data["input_tp"]),
                "input_lra": float(data.get("input_lra", 0)),
            }
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise ValueError(f"Failed to parse loudnorm JSON: {e}")
