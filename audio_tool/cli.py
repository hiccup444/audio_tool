"""Command-line interface for audio-tool."""

import csv
import json
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Prompt

from audio_tool.config import MAX_GAIN_DB, SUPPORTED_INPUT_FORMATS, HARD_CLIP_THRESHOLD_DBFS
from audio_tool.core.audio_file import AudioFile, LoudnessStats, FileProcessingConfig
from audio_tool.core.loudness import LoudnessAnalyzer
from audio_tool.core.processor import AudioProcessor
from audio_tool.core.exporter import AudioExporter, OutputFormat
from audio_tool.utils.ffmpeg import check_ffmpeg

app = typer.Typer(
    name="audio-tool",
    help="EBU R128 loudness analysis and audio conversion tool",
    no_args_is_help=True,
)
console = Console()


class OutputFormatEnum(str, Enum):
    """Output format options."""
    wav = "wav"
    ogg = "ogg"
    flac = "flac"
    mp3 = "mp3"


def collect_audio_files(paths: list[Path], recursive: bool = False) -> list[Path]:
    """Collect all audio files from the given paths.

    Args:
        paths: List of file or directory paths
        recursive: Whether to search directories recursively

    Returns:
        List of audio file paths
    """
    audio_files = []

    for path in paths:
        if path.is_file():
            if path.suffix.lower() in SUPPORTED_INPUT_FORMATS:
                audio_files.append(path)
            else:
                console.print(f"[yellow]Skipping unsupported file: {path}[/yellow]")
        elif path.is_dir():
            if recursive:
                for ext in SUPPORTED_INPUT_FORMATS:
                    audio_files.extend(path.rglob(f"*{ext}"))
            else:
                for ext in SUPPORTED_INPUT_FORMATS:
                    audio_files.extend(path.glob(f"*{ext}"))
        else:
            console.print(f"[red]Path not found: {path}[/red]")

    return sorted(set(audio_files))


def display_loudness_table(
    files: list[tuple[Path, LoudnessStats]],
    title: str = "Loudness Analysis",
) -> None:
    """Display loudness measurements in a table.

    Args:
        files: List of (path, loudness_stats) tuples
        title: Table title
    """
    table = Table(title=title)
    table.add_column("File", style="cyan", no_wrap=True)
    table.add_column("Integrated", justify="right")
    table.add_column("Max Moment.", justify="right")
    table.add_column("Max Short", justify="right")
    table.add_column("True Peak", justify="right")

    for path, stats in files:
        table.add_row(
            path.name,
            f"{stats.integrated_lufs:.1f} LUFS",
            f"{stats.max_momentary_lufs:.1f} LUFS",
            f"{stats.max_short_term_lufs:.1f} LUFS",
            f"{stats.true_peak_dbtp:.1f} dBTP",
        )

    console.print(table)


def display_comparison_table(
    files: list[tuple[Path, LoudnessStats, LoudnessStats, float]],
    title: str = "Before/After Comparison",
) -> None:
    """Display before/after loudness comparison.

    Args:
        files: List of (path, original_stats, processed_stats, gain_applied) tuples
        title: Table title
    """
    table = Table(title=title)
    table.add_column("File", style="cyan", no_wrap=True)
    table.add_column("Gain", justify="right")
    table.add_column("Before", justify="right")
    table.add_column("After", justify="right")
    table.add_column("Max M After", justify="right")
    table.add_column("Max S After", justify="right")
    table.add_column("TP After", justify="right")

    for path, original, processed, gain in files:
        gain_str = f"+{gain:.1f}" if gain >= 0 else f"{gain:.1f}"
        table.add_row(
            path.name,
            f"{gain_str} dB",
            f"{original.integrated_lufs:.1f} LUFS",
            f"{processed.integrated_lufs:.1f} LUFS",
            f"{processed.max_momentary_lufs:.1f} LUFS",
            f"{processed.max_short_term_lufs:.1f} LUFS",
            f"{processed.true_peak_dbtp:.1f} dBTP",
        )

    console.print(table)


def parse_gain_input(input_str: str, current_lufs: float) -> float:
    """Parse user input for gain (either dB or target LUFS).

    Args:
        input_str: User input string (e.g., "+3", "-2.5", "-14 LUFS", "-14LUFS")
        current_lufs: Current integrated loudness for target calculation

    Returns:
        Gain in dB

    Raises:
        ValueError: If input cannot be parsed
    """
    input_str = input_str.strip().upper()

    # Check if it's a target LUFS
    if "LUFS" in input_str:
        target_str = input_str.replace("LUFS", "").strip()
        try:
            target = float(target_str)
            gain = AudioProcessor.calculate_gain_for_target_lufs(current_lufs, target)
            return gain
        except ValueError:
            raise ValueError(f"Invalid LUFS value: {target_str}")

    # Otherwise, treat as dB
    try:
        gain = float(input_str)
        if gain < -MAX_GAIN_DB or gain > MAX_GAIN_DB:
            raise ValueError(f"Gain must be between -{MAX_GAIN_DB} and +{MAX_GAIN_DB} dB")
        return gain
    except ValueError:
        raise ValueError(
            f"Invalid input: {input_str}. "
            f"Use dB (e.g., '+3', '-2') or target LUFS (e.g., '-14 LUFS')"
        )


def load_config_file(config_path: Path) -> list[FileProcessingConfig]:
    """Load processing configuration from CSV or JSON file.

    CSV format:
        file,gain_db,target_lufs
        track1.wav,+3.5,
        track2.ogg,,-14

    JSON format:
        [
            {"file": "track1.wav", "gain_db": 3.5},
            {"file": "track2.ogg", "target_lufs": -14}
        ]

    Args:
        config_path: Path to config file

    Returns:
        List of FileProcessingConfig objects
    """
    configs = []

    if config_path.suffix.lower() == ".json":
        with open(config_path) as f:
            data = json.load(f)

        for item in data:
            config = FileProcessingConfig(
                path=Path(item["file"]),
                gain_db=item.get("gain_db"),
                target_lufs=item.get("target_lufs"),
            )
            configs.append(config)

    elif config_path.suffix.lower() == ".csv":
        with open(config_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                gain_db = None
                target_lufs = None

                if row.get("gain_db"):
                    gain_db = float(row["gain_db"])
                if row.get("target_lufs"):
                    target_lufs = float(row["target_lufs"])

                config = FileProcessingConfig(
                    path=Path(row["file"]),
                    gain_db=gain_db,
                    target_lufs=target_lufs,
                )
                configs.append(config)
    else:
        raise ValueError(f"Unsupported config file format: {config_path.suffix}")

    return configs


@app.command()
def analyze(
    files: Annotated[
        list[Path],
        typer.Argument(help="Audio files or directories to analyze"),
    ],
    recursive: Annotated[
        bool,
        typer.Option("-r", "--recursive", help="Search directories recursively"),
    ] = False,
    output_json: Annotated[
        bool,
        typer.Option("--json", help="Output results as JSON"),
    ] = False,
) -> None:
    """Analyze loudness of audio files (EBU R128).

    Displays integrated loudness, maximum momentary loudness,
    maximum short-term loudness, and true peak for each file.
    """
    if not check_ffmpeg():
        console.print("[red]Error: FFmpeg not found. Please install FFmpeg.[/red]")
        raise typer.Exit(1)

    audio_files = collect_audio_files(files, recursive)

    if not audio_files:
        console.print("[yellow]No audio files found.[/yellow]")
        raise typer.Exit(0)

    console.print(f"Found {len(audio_files)} audio file(s)\n")

    analyzer = LoudnessAnalyzer()
    results: list[tuple[Path, LoudnessStats]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Analyzing...", total=len(audio_files))

        for file_path in audio_files:
            progress.update(task, description=f"Analyzing {file_path.name}...")
            try:
                stats = analyzer.analyze_file(file_path)
                results.append((file_path, stats))
            except Exception as e:
                console.print(f"[red]Error analyzing {file_path}: {e}[/red]")
            progress.advance(task)

    if output_json:
        json_results = [
            {
                "file": str(path),
                "integrated_lufs": stats.integrated_lufs,
                "max_momentary_lufs": stats.max_momentary_lufs,
                "max_short_term_lufs": stats.max_short_term_lufs,
                "true_peak_dbtp": stats.true_peak_dbtp,
            }
            for path, stats in results
        ]
        console.print(json.dumps(json_results, indent=2))
    else:
        display_loudness_table(results)


@app.command()
def process(
    files: Annotated[
        Optional[list[Path]],
        typer.Argument(help="Audio files or directories to process"),
    ] = None,
    output_dir: Annotated[
        Path,
        typer.Option("-o", "--output", help="Output directory"),
    ] = ...,
    format: Annotated[
        OutputFormatEnum,
        typer.Option("-f", "--format", help="Output format"),
    ] = OutputFormatEnum.wav,
    config: Annotated[
        Optional[Path],
        typer.Option("--config", help="Config file (CSV or JSON) with per-file settings"),
    ] = None,
    hard_clip: Annotated[
        bool,
        typer.Option("--clip", help=f"Apply hard clipper at {HARD_CLIP_THRESHOLD_DBFS} dBFS"),
    ] = False,
    recursive: Annotated[
        bool,
        typer.Option("-r", "--recursive", help="Search directories recursively"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview without exporting"),
    ] = False,
) -> None:
    """Process and export audio files with gain adjustment.

    In interactive mode (no --config), you'll be prompted to enter
    gain adjustments for each file after seeing their loudness.

    With --config, settings are read from a CSV or JSON file.
    """
    if not check_ffmpeg():
        console.print("[red]Error: FFmpeg not found. Please install FFmpeg.[/red]")
        raise typer.Exit(1)

    # Collect files
    if config:
        # Load from config file
        configs = load_config_file(config)
        audio_files = [c.path for c in configs]
        config_map = {c.path.name: c for c in configs}
    else:
        if not files:
            console.print("[red]Error: Provide audio files or use --config[/red]")
            raise typer.Exit(1)
        audio_files = collect_audio_files(files, recursive)
        config_map = {}

    if not audio_files:
        console.print("[yellow]No audio files found.[/yellow]")
        raise typer.Exit(0)

    console.print(f"Found {len(audio_files)} audio file(s)\n")

    analyzer = LoudnessAnalyzer()
    processor = AudioProcessor()
    exporter = AudioExporter()

    # Step 1: Analyze all files
    console.print("[bold]Step 1: Analyzing original loudness...[/bold]\n")

    analyzed_files: list[tuple[AudioFile, LoudnessStats]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Analyzing...", total=len(audio_files))

        for file_path in audio_files:
            progress.update(task, description=f"Analyzing {file_path.name}...")
            try:
                audio_file = AudioFile.from_file(file_path)
                stats = analyzer.analyze_file(file_path)
                audio_file.original_loudness = stats
                analyzed_files.append((audio_file, stats))
            except Exception as e:
                console.print(f"[red]Error loading {file_path}: {e}[/red]")
            progress.advance(task)

    # Display original loudness
    display_loudness_table(
        [(af.path, stats) for af, stats in analyzed_files],
        title="Original Loudness"
    )

    # Step 2: Get gain adjustments (interactive or from config)
    console.print("\n[bold]Step 2: Setting gain adjustments...[/bold]\n")

    file_gains: list[tuple[AudioFile, float]] = []

    if config_map:
        # Use config file settings
        for audio_file, stats in analyzed_files:
            file_config = config_map.get(audio_file.path.name)
            if file_config is None:
                console.print(f"[yellow]No config for {audio_file.path.name}, skipping[/yellow]")
                continue

            if file_config.target_lufs is not None:
                gain = processor.calculate_gain_for_target_lufs(
                    stats.integrated_lufs,
                    file_config.target_lufs
                )
                console.print(
                    f"{audio_file.path.name}: "
                    f"Target {file_config.target_lufs} LUFS -> {gain:+.1f} dB"
                )
            elif file_config.gain_db is not None:
                gain = file_config.gain_db
                console.print(f"{audio_file.path.name}: Manual {gain:+.1f} dB")
            else:
                console.print(f"[yellow]{audio_file.path.name}: No adjustment specified[/yellow]")
                gain = 0.0

            file_gains.append((audio_file, gain))
    else:
        # Interactive mode
        console.print(
            "Enter gain for each file. Use dB values (e.g., '+3', '-2') "
            "or target LUFS (e.g., '-14 LUFS').\n"
            "Press Enter to skip (no change).\n"
        )

        for audio_file, stats in analyzed_files:
            while True:
                user_input = Prompt.ask(
                    f"[cyan]{audio_file.path.name}[/cyan] "
                    f"(current: {stats.integrated_lufs:.1f} LUFS)",
                    default="0",
                )

                try:
                    gain = parse_gain_input(user_input, stats.integrated_lufs)
                    break
                except ValueError as e:
                    console.print(f"[red]{e}[/red]")

            file_gains.append((audio_file, gain))

    if not file_gains:
        console.print("[yellow]No files to process.[/yellow]")
        raise typer.Exit(0)

    # Step 3: Process and preview
    console.print("\n[bold]Step 3: Processing and previewing...[/bold]\n")

    processed_files: list[tuple[AudioFile, LoudnessStats, LoudnessStats, float]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Processing...", total=len(file_gains))

        for audio_file, gain in file_gains:
            progress.update(task, description=f"Processing {audio_file.path.name}...")

            # Apply processing
            processed_data = processor.process(
                audio_file.data,
                gain_db=gain,
                apply_hard_clip=hard_clip,
            )
            audio_file.data = processed_data
            audio_file.gain_applied_db = gain
            audio_file.hard_clip_applied = hard_clip

            # Analyze processed audio
            audio_bytes = processed_data.astype("<f4").tobytes()
            processed_stats = analyzer.analyze_audio_data(
                audio_bytes,
                audio_file.sample_rate,
                audio_file.channels,
            )
            audio_file.processed_loudness = processed_stats

            processed_files.append((
                audio_file,
                audio_file.original_loudness,
                processed_stats,
                gain,
            ))

            progress.advance(task)

    # Display comparison
    display_comparison_table(
        [(af.path, orig, proc, gain) for af, orig, proc, gain in processed_files],
        title="Before/After Comparison" + (" (with clipper)" if hard_clip else "")
    )

    if dry_run:
        console.print("\n[yellow]Dry run - no files exported.[/yellow]")
        raise typer.Exit(0)

    # Step 4: Export
    console.print(f"\n[bold]Step 4: Exporting to {format.value.upper()}...[/bold]\n")

    output_dir.mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Exporting...", total=len(processed_files))

        for audio_file, _, _, _ in processed_files:
            progress.update(task, description=f"Exporting {audio_file.path.name}...")

            output_path = output_dir / audio_file.path.stem

            try:
                exported = exporter.export(
                    audio_file.data,
                    audio_file.sample_rate,
                    output_path,
                    format.value,
                )
                console.print(f"  [green]✓[/green] {exported.name}")
            except Exception as e:
                console.print(f"  [red]✗[/red] {audio_file.path.name}: {e}")

            progress.advance(task)

    console.print(f"\n[green]Done! Exported {len(processed_files)} file(s) to {output_dir}[/green]")


@app.command()
def preview(
    file: Annotated[
        Path,
        typer.Argument(help="Audio file to preview"),
    ],
    gain: Annotated[
        Optional[float],
        typer.Option("-g", "--gain", help="Gain adjustment in dB"),
    ] = None,
    target: Annotated[
        Optional[float],
        typer.Option("-t", "--target", help="Target integrated LUFS"),
    ] = None,
    hard_clip: Annotated[
        bool,
        typer.Option("--clip", help=f"Apply hard clipper at {HARD_CLIP_THRESHOLD_DBFS} dBFS"),
    ] = False,
) -> None:
    """Preview loudness after applying gain without exporting.

    Shows before/after loudness comparison for a single file.
    """
    if not check_ffmpeg():
        console.print("[red]Error: FFmpeg not found. Please install FFmpeg.[/red]")
        raise typer.Exit(1)

    if gain is not None and target is not None:
        console.print("[red]Error: Specify either --gain or --target, not both[/red]")
        raise typer.Exit(1)

    if gain is None and target is None:
        console.print("[red]Error: Specify --gain or --target[/red]")
        raise typer.Exit(1)

    if not file.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    analyzer = LoudnessAnalyzer()
    processor = AudioProcessor()

    # Load and analyze original
    console.print(f"Loading {file.name}...")
    audio_file = AudioFile.from_file(file)
    original_stats = analyzer.analyze_file(file)

    # Calculate gain
    if target is not None:
        actual_gain = processor.calculate_gain_for_target_lufs(
            original_stats.integrated_lufs,
            target
        )
        console.print(f"Target: {target} LUFS -> Calculated gain: {actual_gain:+.1f} dB")
    else:
        actual_gain = gain

    # Check for clipping
    if processor.will_clip(audio_file.data, actual_gain) and not hard_clip:
        console.print(
            f"[yellow]Warning: This gain will cause clipping. "
            f"Consider using --clip to enable hard clipper.[/yellow]"
        )

    # Process
    console.print("Processing...")
    processed_data = processor.process(
        audio_file.data,
        gain_db=actual_gain,
        apply_hard_clip=hard_clip,
    )

    # Analyze processed
    console.print("Analyzing processed audio...")
    audio_bytes = processed_data.astype("<f4").tobytes()
    processed_stats = analyzer.analyze_audio_data(
        audio_bytes,
        audio_file.sample_rate,
        audio_file.channels,
    )

    # Display comparison
    console.print()
    display_comparison_table(
        [(file, original_stats, processed_stats, actual_gain)],
        title="Preview" + (" (with clipper)" if hard_clip else "")
    )


@app.callback()
def main() -> None:
    """EBU R128 loudness analysis and audio conversion tool."""
    pass


if __name__ == "__main__":
    app()
