"""Tests for video_maker.encoder module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

from video_maker.encoder import (
    validate_inputs,
    _prepare_image,
    encode_video,
    batch_encode,
    resolve_quality,
    BatchResult,
)
from video_maker.settings import QUALITY_PRESETS


# --- resolve_quality ---

def test_resolve_quality_1080p() -> None:
    preset = resolve_quality("1080p")
    assert preset["resolution"] == (1920, 1080)
    assert preset["video_bitrate"] == "8M"


def test_resolve_quality_4k() -> None:
    preset = resolve_quality("4k")
    assert preset["resolution"] == (3840, 2160)
    assert preset["video_bitrate"] == "35M"


def test_resolve_quality_invalid() -> None:
    with pytest.raises(ValueError, match="Unknown quality"):
        resolve_quality("720p")


# --- validate_inputs ---

def test_validate_inputs_success(tmp_image: Path, tmp_audio: Path) -> None:
    validate_inputs(tmp_image, tmp_audio)


def test_validate_inputs_missing_image(tmp_audio: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Image file not found"):
        validate_inputs(Path("/nonexistent.jpg"), tmp_audio)


def test_validate_inputs_missing_audio(tmp_image: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Audio file not found"):
        validate_inputs(tmp_image, Path("/nonexistent.mp3"))


def test_validate_inputs_bad_image_extension(tmp_path: Path, tmp_audio: Path) -> None:
    bad_img = tmp_path / "image.gif"
    bad_img.write_bytes(b"\x00")
    with pytest.raises(ValueError, match="Unsupported image format"):
        validate_inputs(bad_img, tmp_audio)


def test_validate_inputs_bad_audio_extension(tmp_image: Path, tmp_path: Path) -> None:
    bad_audio = tmp_path / "sound.mid"
    bad_audio.write_bytes(b"\x00")
    with pytest.raises(ValueError, match="Unsupported audio format"):
        validate_inputs(tmp_image, bad_audio)


# --- _prepare_image ---

def test_prepare_image_already_correct_size(tmp_path: Path) -> None:
    w, h = QUALITY_PRESETS["1080p"]["resolution"]
    img = Image.new("RGB", (w, h), (0, 128, 255))
    path = tmp_path / "exact.png"
    img.save(path)
    result = _prepare_image(path, tmp_path, (w, h))
    assert result == path


def test_prepare_image_resizes_and_pads(tmp_path: Path) -> None:
    img = Image.new("RGB", (400, 400), (0, 255, 0))
    path = tmp_path / "square.jpg"
    img.save(path)
    result = _prepare_image(path, tmp_path, (1920, 1080))
    assert result != path
    prepared = Image.open(result)
    assert prepared.size == (1920, 1080)


def test_prepare_image_wider_than_16_9(tmp_path: Path) -> None:
    img = Image.new("RGB", (3000, 1000), (255, 0, 0))
    path = tmp_path / "wide.png"
    img.save(path)
    result = _prepare_image(path, tmp_path, (1920, 1080))
    prepared = Image.open(result)
    assert prepared.size == (1920, 1080)


def test_prepare_image_4k_resolution(tmp_path: Path) -> None:
    img = Image.new("RGB", (800, 600), (100, 100, 100))
    path = tmp_path / "small.png"
    img.save(path)
    result = _prepare_image(path, tmp_path, (3840, 2160))
    prepared = Image.open(result)
    assert prepared.size == (3840, 2160)


def test_prepare_image_taller_than_16_9(tmp_path: Path) -> None:
    img = Image.new("RGB", (500, 2000), (0, 0, 255))
    path = tmp_path / "tall.png"
    img.save(path)
    result = _prepare_image(path, tmp_path, (1920, 1080))
    assert result != path
    prepared = Image.open(result)
    assert prepared.size == (1920, 1080)


# --- encode_video ---

def test_encode_video_success(tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock) -> None:
    output = tmp_path / "output.mp4"

    with patch("video_maker.encoder.subprocess.run", return_value=mock_ffmpeg_ok) as mock_run, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        output_path = encode_video(tmp_image, tmp_audio, output)

    assert output_path == output.resolve()
    mock_run.assert_called_once()

    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "ffmpeg"
    assert "libx264" in cmd
    assert "aac" in cmd
    assert "-shortest" in cmd
    assert "+faststart" in cmd


def test_encode_video_4k(tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock) -> None:
    output = tmp_path / "output_4k.mp4"

    with patch("video_maker.encoder.subprocess.run", return_value=mock_ffmpeg_ok) as mock_run, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        encode_video(tmp_image, tmp_audio, output, quality="4k")

    cmd = mock_run.call_args[0][0]
    assert "35M" in cmd


def test_encode_video_ffmpeg_fails(tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_fail: MagicMock) -> None:
    output = tmp_path / "fail.mp4"

    with patch("video_maker.encoder.subprocess.run", return_value=mock_ffmpeg_fail), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            encode_video(tmp_image, tmp_audio, output)


def test_encode_video_no_ffmpeg(tmp_image: Path, tmp_audio: Path, tmp_path: Path) -> None:
    output = tmp_path / "nope.mp4"

    with patch("video_maker.encoder.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="ffmpeg is not installed"):
            encode_video(tmp_image, tmp_audio, output)


# --- batch_encode ---

def test_batch_encode_success(batch_dir: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock) -> None:
    output_dir = tmp_path / "videos_out"

    with patch("video_maker.encoder.subprocess.run", return_value=mock_ffmpeg_ok), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        result = batch_encode(batch_dir, output_dir, quality="1080p")

    assert isinstance(result, BatchResult)
    assert len(result.successes) == 3
    assert len(result.failures) == 0
    for path in result.successes:
        assert path.suffix == ".mp4"
        assert output_dir in path.parents


def test_batch_encode_no_cover(tmp_path: Path) -> None:
    audio_dir = tmp_path / "no_cover"
    audio_dir.mkdir()
    (audio_dir / "song.mp3").write_bytes(b"\x00")

    with pytest.raises(FileNotFoundError, match="No cover image"):
        batch_encode(audio_dir, tmp_path / "out")


def test_batch_encode_no_audio(tmp_path: Path) -> None:
    audio_dir = tmp_path / "no_audio"
    audio_dir.mkdir()
    img = Image.new("RGB", (100, 100))
    img.save(audio_dir / "cover.png")

    with pytest.raises(FileNotFoundError, match="No audio files"):
        batch_encode(audio_dir, tmp_path / "out")


def test_batch_encode_dir_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Input directory not found"):
        batch_encode(tmp_path / "nonexistent", tmp_path / "out")


def test_batch_encode_not_a_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "somefile.txt"
    file_path.write_text("not a dir")
    with pytest.raises(NotADirectoryError, match="Input path is not a directory"):
        batch_encode(file_path, tmp_path / "out")


def test_batch_encode_partial_failure(batch_dir: Path, tmp_path: Path) -> None:
    """Test that batch_encode returns structured result when some files fail."""
    output_dir = tmp_path / "partial_out"
    call_count = 0

    def _mock_run(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 2:
            result.returncode = 1
            result.stderr = "encode error"
        else:
            result.returncode = 0
            result.stderr = ""
        return result

    with patch("video_maker.encoder.subprocess.run", side_effect=_mock_run), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        result = batch_encode(batch_dir, output_dir, quality="1080p")

    assert isinstance(result, BatchResult)
    assert len(result.successes) == 2
    assert len(result.failures) == 1
    assert result.failures[0][0].suffix in {".mp3", ".wav", ".flac"}
