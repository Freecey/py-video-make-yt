"""YouTube-optimized encoding settings and quality presets."""

from __future__ import annotations

from typing import TypedDict


class QualityPreset(TypedDict):
    resolution: tuple[int, int]
    video_bitrate: str
    frame_rate: int


SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".m4a", ".ogg", ".opus", ".flac", ".wma"}
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}

# Batch mode: optional manifest listing audio + image per track
TRACKS_MANIFEST_FILENAME = "tracks.json"

QUALITY_PRESETS: dict[str, QualityPreset] = {
    "1080p": {
        "resolution": (1920, 1080),
        "video_bitrate": "8M",
        "frame_rate": 30,
    },
    "4k": {
        "resolution": (3840, 2160),
        "video_bitrate": "35M",
        "frame_rate": 30,
    },
}

ENCODING_SETTINGS = {
    "video_codec": "libx264",
    "audio_codec": "aac",
    "audio_bitrate": "384k",
    "audio_sample_rate": 48000,
    "audio_channels": 2,
    "profile": "high",
    "preset": "slow",
    "pix_fmt": "yuv420p",
    "movflags": "+faststart",
}
