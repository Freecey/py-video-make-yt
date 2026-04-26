"""Integration tests that run real ffmpeg. Skipped by default (use -m integration)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PIL import Image

from video_maker.encoder import encode_video, check_ffmpeg_available


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True, scope="module")
def _require_ffmpeg() -> None:
    """Skip all integration tests if ffmpeg is not installed."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")


@pytest.fixture()
def real_image(tmp_path: Path) -> Path:
    img = Image.new("RGB", (640, 360), (30, 60, 90))
    p = tmp_path / "cover.png"
    img.save(p, "PNG")
    return p


@pytest.fixture()
def real_audio(tmp_path: Path) -> Path:
    """Generate a 1-second sine wave audio using ffmpeg."""
    audio_path = tmp_path / "tone.mp3"
    import subprocess

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "sine=frequency=440:duration=1",
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            str(audio_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return audio_path


def test_encode_video_real_ffmpeg(real_image: Path, real_audio: Path, tmp_path: Path) -> None:
    output = tmp_path / "output.mp4"
    check_ffmpeg_available.cache_clear()
    result = encode_video(real_image, real_audio, output)
    assert result.exists()
    assert result.stat().st_size > 0


def test_encode_video_real_with_normalize(real_image: Path, real_audio: Path, tmp_path: Path) -> None:
    output = tmp_path / "normalized.mp4"
    check_ffmpeg_available.cache_clear()
    result = encode_video(real_image, real_audio, output, normalize=True)
    assert result.exists()


def test_encode_video_real_with_thumbnail(real_image: Path, real_audio: Path, tmp_path: Path) -> None:
    output = tmp_path / "thumb_video.mp4"
    check_ffmpeg_available.cache_clear()
    result = encode_video(real_image, real_audio, output, generate_thumbnail=True)
    assert result.exists()
    thumb = tmp_path / "thumb_video_thumbnail.jpg"
    assert thumb.exists()
    thumb_img = Image.open(thumb)
    assert thumb_img.size == (1280, 720)
