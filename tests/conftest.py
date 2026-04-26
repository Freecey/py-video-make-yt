"""Shared test fixtures for video-maker-auto tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image


@pytest.fixture(autouse=True)
def mock_get_audio_duration():
    """Mock _get_audio_duration to avoid calling real ffprobe in tests."""
    with patch("video_maker.encoder._get_audio_duration", return_value=None):
        yield


@pytest.fixture(autouse=True)
def mock_check_ffmpeg():
    """Mock check_ffmpeg_available to avoid calling real ffmpeg in tests."""
    with patch("video_maker.encoder.check_ffmpeg_available", return_value="/usr/bin/ffmpeg"):
        yield


@pytest.fixture
def tmp_image(tmp_path: Path) -> Path:
    img = Image.new("RGB", (800, 600), color=(255, 0, 0))
    path = tmp_path / "cover.jpg"
    img.save(path)
    return path


@pytest.fixture
def tmp_audio(tmp_path: Path) -> Path:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"\x00" * 1024)
    return audio_path


@pytest.fixture
def batch_dir(tmp_path: Path) -> Path:
    """Create a folder with 3 audio files and a cover image."""
    img = Image.new("RGB", (1200, 800), (40, 80, 160))
    img.save(tmp_path / "cover.png")
    for name in ["track01.mp3", "track02.wav", "track03.flac"]:
        (tmp_path / name).write_bytes(b"\x00" * 512)
    return tmp_path


@pytest.fixture
def mock_ffmpeg_ok() -> MagicMock:
    """A mock Popen result indicating ffmpeg success."""
    process = MagicMock()
    process.stderr = iter([])
    process.wait.return_value = 0
    return process


@pytest.fixture
def mock_ffmpeg_fail() -> MagicMock:
    """A mock Popen result indicating ffmpeg failure."""
    process = MagicMock()
    process.stderr = iter(["Error: something went wrong\n"])
    process.wait.return_value = 1
    return process
