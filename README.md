# Audio Tool

A command-line tool for batch audio processing with EBU R128 loudness analysis, per-file gain adjustment, and multi-format export.

## Features

- **EBU R128 Loudness Analysis** - Measure integrated, maximum momentary, and maximum short-term loudness in LUFS
- **Per-File Gain Adjustment** - Apply ±12dB gain to each file independently
- **Target Loudness Normalization** - Automatically calculate gain to reach a target LUFS
- **Hard Clipper** - Optional limiter at -0.3 dBFS to prevent inter-sample peaks
- **Batch Processing** - Process hundreds of files at once
- **Multiple Export Formats** - WAV, OGG, FLAC, MP3

## Requirements

- Python 3.10+
- FFmpeg (must be installed and in your PATH)

## Installation

- download zip, extract to wherever. Open console inside of audio_tool folder.

```bash
cd audio_tool
pip install -e .
```

## Commands

### analyze

Analyze loudness of audio files without modifying them.

```bash
# Analyze a single file
audio-tool analyze song.wav

# Analyze multiple files
audio-tool analyze track1.wav track2.ogg track3.wav

# Analyze all audio files in a directory
audio-tool analyze ./my_audio_folder

# Analyze recursively (includes subdirectories)
audio-tool analyze ./my_audio_folder -r

# Output as JSON (useful for scripting)
audio-tool analyze *.wav --json
```

**Output:**
```
┌─────────────┬────────────┬─────────────┬────────────┬───────────┐
│ File        │ Integrated │ Max Moment. │ Max Short  │ True Peak │
├─────────────┼────────────┼─────────────┼────────────┼───────────┤
│ track1.wav  │ -18.2 LUFS │ -12.4 LUFS  │ -14.1 LUFS │ -0.8 dBTP │
│ track2.ogg  │ -14.5 LUFS │ -8.2 LUFS   │ -10.3 LUFS │ -0.1 dBTP │
└─────────────┴────────────┴─────────────┴────────────┴───────────┘
```

### process

Process audio files with gain adjustment and export to a new format.

#### Interactive Mode

When you don't provide a config file, the tool runs interactively:

```bash
audio-tool process *.wav -o ./output -f flac
```

1. Analyzes all files and displays their loudness
2. Prompts you to enter a gain value for each file
3. Shows a before/after comparison
4. Exports the processed files

**Gain input formats:**
- `+3` or `3` - Apply +3 dB gain
- `-2.5` - Apply -2.5 dB gain
- `-14 LUFS` - Normalize to -14 LUFS (auto-calculates gain)
- `0` or Enter - No change

#### Config File Mode

For repeatable batch processing, use a config file:

```bash
audio-tool process --config batch.csv -o ./output -f mp3
```

**CSV format:**
```csv
file,gain_db,target_lufs
track1.wav,+3.5,
track2.ogg,,-14
track3.wav,-2.0,
```

**JSON format:**
```json
[
  {"file": "track1.wav", "gain_db": 3.5},
  {"file": "track2.ogg", "target_lufs": -14},
  {"file": "track3.wav", "gain_db": -2.0}
]
```

Note: Specify either `gain_db` OR `target_lufs` for each file, not both.

#### Options

| Option | Description |
|--------|-------------|
| `-o, --output` | Output directory (required) |
| `-f, --format` | Output format: `wav`, `ogg`, `flac`, `mp3` (default: wav) |
| `--config` | Path to CSV or JSON config file |
| `--clip` | Enable hard clipper at -0.3 dBFS |
| `-r, --recursive` | Search directories recursively |
| `--dry-run` | Preview without exporting |

#### Examples

```bash
# Interactive, export as FLAC with hard clipper
audio-tool process *.wav -o ./normalized -f flac --clip

# Using config file, export as MP3
audio-tool process --config settings.csv -o ./output -f mp3

# Dry run to preview what would happen
audio-tool process *.ogg -o ./out -f wav --dry-run

# Process entire folder recursively
audio-tool process ./raw_audio -r -o ./processed -f ogg --clip
```

### preview

Preview the effect of a gain adjustment on a single file without exporting.

```bash
# Preview +6 dB gain
audio-tool preview song.wav -g 6.0

# Preview normalization to -14 LUFS
audio-tool preview song.wav -t -14

# Preview with hard clipper enabled
audio-tool preview song.wav -g 8.0 --clip
```

**Output:**
```
┌───────────┬────────┬─────────────┬─────────────┬─────────────┬───────────┐
│ File      │ Gain   │ Before      │ After       │ Max M After │ TP After  │
├───────────┼────────┼─────────────┼─────────────┼─────────────┼───────────┤
│ song.wav  │ +6.0dB │ -20.0 LUFS  │ -14.0 LUFS  │ -8.2 LUFS   │ -0.3 dBTP │
└───────────┴────────┴─────────────┴─────────────┴─────────────┴───────────┘
```

## Loudness Terminology

| Term | Description |
|------|-------------|
| **Integrated LUFS** | Overall loudness of the entire file (EBU R128) |
| **Momentary LUFS** | Loudness measured over 400ms windows |
| **Short-term LUFS** | Loudness measured over 3-second windows |
| **True Peak (dBTP)** | Maximum sample peak including inter-sample peaks |
| **dBFS** | Decibels relative to full scale (0 dBFS = maximum digital level) |

## Common Workflows

### Normalize a batch of files to -14 LUFS

Create a config file `normalize.csv`:
```csv
file,gain_db,target_lufs
song1.wav,,-14
song2.wav,,-14
song3.wav,,-14
```

Then run:
```bash
audio-tool process --config normalize.csv -o ./normalized -f wav --clip
```

### Analyze files, then decide on adjustments

```bash
# First, analyze everything
audio-tool analyze ./my_songs -r

# Then process interactively based on what you see
audio-tool process ./my_songs -r -o ./output -f flac
```

### Quick loudness check for a single file

```bash
audio-tool analyze song.wav
```

### Preview different gain values before committing

```bash
audio-tool preview song.wav -g 3
audio-tool preview song.wav -g 6
audio-tool preview song.wav -t -14 --clip
```

## Hard Clipper

The `--clip` flag enables a hard clipper at -0.3 dBFS. This:

- Prevents any sample from exceeding -0.3 dBFS
- Helps avoid inter-sample peaks that can cause distortion in lossy codecs
- Is applied **after** gain adjustment

Use it when:
- Applying significant positive gain
- Exporting to lossy formats (MP3, OGG)
- You want guaranteed headroom

## Supported Formats

**Input:** WAV, OGG, FLAC

**Output:** WAV, OGG, FLAC, MP3

## Troubleshooting

### "FFmpeg not found"

Install FFmpeg and ensure it's in your PATH:
- Windows: Download from https://ffmpeg.org/download.html, extract, and add the `bin` folder to your PATH
- macOS: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg` or equivalent

### Empty or corrupted output files

Ensure you have write permissions to the output directory and sufficient disk space.
