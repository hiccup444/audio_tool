"""Configuration constants for audio-tool."""

# Hard clipper threshold in dBFS
HARD_CLIP_THRESHOLD_DBFS = -0.3

# Maximum allowed gain adjustment in dB
MAX_GAIN_DB = 12.0

# Supported input formats
SUPPORTED_INPUT_FORMATS = {".wav", ".ogg", ".flac"}

# Supported output formats
SUPPORTED_OUTPUT_FORMATS = {"wav", "ogg", "flac", "mp3"}

# FFmpeg codec mappings
FFMPEG_CODECS = {
    "wav": "pcm_s16le",
    "ogg": "libvorbis",
    "flac": "flac",
    "mp3": "libmp3lame",
}

# Default quality settings
DEFAULT_QUALITY = {
    "ogg": "6",      # VBR quality 0-10
    "mp3": "320k",   # Bitrate
    "flac": "5",     # Compression level
}
