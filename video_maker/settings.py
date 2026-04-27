"""YouTube-optimized encoding settings and quality presets."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class QualityPreset:
    resolution: tuple[int, int]
    video_bitrate: str
    frame_rate: int


@dataclasses.dataclass(frozen=True)
class EncodingSettings:
    video_codec: str
    audio_codec: str
    audio_bitrate: str
    audio_sample_rate: int
    audio_channels: int
    profile: str
    preset: str
    pix_fmt: str
    movflags: str


SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".m4a", ".ogg", ".opus", ".flac", ".wma"}
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}

# Batch mode: optional manifest listing audio + image per track
TRACKS_MANIFEST_FILENAME = "tracks.json"

QUALITY_PRESETS: dict[str, QualityPreset] = {
    "1080p": QualityPreset(
        resolution=(1920, 1080),
        video_bitrate="8M",
        frame_rate=30,
    ),
    "4k": QualityPreset(
        resolution=(3840, 2160),
        video_bitrate="35M",
        frame_rate=30,
    ),
    "shorts": QualityPreset(
        resolution=(1080, 1920),
        video_bitrate="8M",
        frame_rate=30,
    ),
    "shorts4k": QualityPreset(
        resolution=(2160, 3840),
        video_bitrate="35M",
        frame_rate=30,
    ),
}

# Blurred background: Gaussian blur radius applied to the cover-scaled background image.
# Higher = stronger blur. Tune here without touching encoder logic.
BLUR_BACKGROUND_RADIUS: int = 40

ENCODING_SETTINGS = EncodingSettings(
    video_codec="libx264",
    audio_codec="aac",
    audio_bitrate="384k",
    audio_sample_rate=48000,
    audio_channels=2,
    profile="high",
    preset="slow",
    pix_fmt="yuv420p",
    movflags="+faststart",
)

# EBU R128 loudness normalization (YouTube standard)
LOUDNORM_TARGET_I: float = -14.0  # Integrated loudness (LUFS)
LOUDNORM_TARGET_TP: float = -1.0  # True Peak (dBTP)
LOUDNORM_TARGET_LRA: float = 11.0  # Loudness Range (LU)

# Text overlay defaults (drawtext filter)
TEXT_OVERLAY_FONT_SIZE: int = 36
TEXT_OVERLAY_FONT_COLOR: str = "white"
TEXT_OVERLAY_BORDER_COLOR: str = "black"
TEXT_OVERLAY_BORDER_WIDTH: int = 2
TEXT_OVERLAY_Y_OFFSET: int = 50  # pixels from bottom

# Thumbnail generation
THUMBNAIL_SIZE: tuple[int, int] = (1280, 720)
THUMBNAIL_SUFFIX: str = "_thumbnail"
THUMBNAIL_FORMAT: str = "JPEG"
