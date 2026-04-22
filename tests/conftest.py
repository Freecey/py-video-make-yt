"""Shared test fixtures for video-maker-auto tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image


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
    """A mock subprocess result indicating ffmpeg success."""
    result = MagicMock()
    result.returncode = 0
    result.stderr = ""
    return result


@pytest.fixture
def mock_ffmpeg_fail() -> MagicMock:
    """A mock subprocess result indicating ffmpeg failure."""
    result = MagicMock()
    result.returncode = 1
    result.stderr = "Error: something went wrong"
    return result
