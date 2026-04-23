"""Tests for video_maker.encoder module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

import json

from video_maker.encoder import (
    validate_inputs,
    _prepare_image,
    _resolve_track_pairs,
    encode_video,
    batch_encode,
    resolve_quality,
    BatchResult,
)
from video_maker.settings import TRACKS_MANIFEST_FILENAME
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


def test_resolve_quality_case_insensitive() -> None:
    assert resolve_quality("1080P")["resolution"] == (1920, 1080)
    assert resolve_quality("4K")["resolution"] == (3840, 2160)


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


def test_validate_inputs_image_is_directory(tmp_path: Path, tmp_audio: Path) -> None:
    d = tmp_path / "notafile.jpg"
    d.mkdir()
    with pytest.raises(ValueError, match="not a file"):
        validate_inputs(d, tmp_audio)


def test_validate_inputs_audio_is_directory(tmp_image: Path, tmp_path: Path) -> None:
    d = tmp_path / "notafile.mp3"
    d.mkdir()
    with pytest.raises(ValueError, match="not a file"):
        validate_inputs(tmp_image, d)


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


def test_prepare_image_corrupt_raises(tmp_path: Path, tmp_audio: Path) -> None:
    bad_img = tmp_path / "corrupt.jpg"
    bad_img.write_bytes(b"not an image at all \x00\x01\x02")
    with pytest.raises(ValueError, match="Cannot read image"):
        with patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
            encode_video(bad_img, tmp_audio, tmp_path / "out.mp4")


def test_prepare_image_zero_dimension_raises(tmp_path: Path) -> None:
    """_prepare_image must raise ValueError for degenerate 0-dimension images."""
    bad = tmp_path / "zero.png"
    # Create a valid 1x1 image and patch Image.open to return a zero-size mock
    with patch("video_maker.encoder.Image.open") as mock_open:
        mock_img = MagicMock()
        mock_img.width = 0
        mock_img.height = 0
        mock_img.convert.return_value = mock_img
        mock_open.return_value.__enter__ = lambda s: mock_img
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        mock_img.size = (0, 0)
        with pytest.raises(ValueError, match="invalid dimensions"):
            _prepare_image(bad, tmp_path, (1920, 1080))


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
    map_at = [i for i, x in enumerate(cmd) if x == "-map"]
    assert len(map_at) == 2
    assert cmd[map_at[0] + 1] == "0:v:0"
    assert cmd[map_at[1] + 1] == "1:a:0"
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

    result = batch_encode(audio_dir, tmp_path / "out")
    assert len(result.successes) == 0
    assert len(result.failures) == 1
    assert result.failures[0][0].name == "song.mp3"
    assert "No image" in result.failures[0][1]


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


# --- _resolve_track_pairs ---

def test_resolve_track_pairs_name_match_and_cover_fallback(tmp_path: Path) -> None:
    (tmp_path / "cover.png").write_bytes(b"png")
    (tmp_path / "a.mp3").write_bytes(b"\x00")
    (tmp_path / "b.mp3").write_bytes(b"\x00")
    img = Image.new("RGB", (10, 10), (1, 2, 3))
    img.save(tmp_path / "b.png")
    items, pre, mode = _resolve_track_pairs(tmp_path, "cover")
    assert mode == "scan"
    assert len(pre) == 0
    assert len(items) == 2
    by_stem = {i.audio_path.stem: i for i in items}
    assert by_stem["a"].image_path.name == "cover.png"
    assert by_stem["b"].image_path.name == "b.png"


def test_resolve_track_pairs_manifest_per_track_image(tmp_path: Path) -> None:
    (tmp_path / "cover.png").write_bytes(b"png")
    (tmp_path / "x.mp3").write_bytes(b"\x00")
    img = Image.new("RGB", (5, 5), (9, 9, 9))
    img.save(tmp_path / "art.png")
    manifest = {
        "default_cover": "cover.png",
        "tracks": [
            {"audio": "x.mp3", "image": "art.png", "output": "outvid"},
        ],
    }
    (tmp_path / TRACKS_MANIFEST_FILENAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    items, pre, mode = _resolve_track_pairs(tmp_path, "cover")
    assert mode == "manifest"
    assert pre == []
    assert len(items) == 1
    assert items[0].output_filename == "outvid.mp4"
    assert items[0].image_path.name == "art.png"


def test_resolve_track_pairs_manifest_default_cover(tmp_path: Path) -> None:
    (tmp_path / "d.jpg").write_bytes(b"jpg")
    (tmp_path / "s.mp3").write_bytes(b"\x00")
    manifest = {
        "default_cover": "d.jpg",
        "tracks": [{"audio": "s.mp3"}],
    }
    (tmp_path / TRACKS_MANIFEST_FILENAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    items, pre, mode = _resolve_track_pairs(tmp_path, "cover")
    assert mode == "manifest"
    assert len(items) == 1
    assert items[0].image_path.name == "d.jpg"


def test_resolve_track_pairs_manifest_no_image_pre_failure(tmp_path: Path) -> None:
    (tmp_path / "s.mp3").write_bytes(b"\x00")
    manifest = {"tracks": [{"audio": "s.mp3"}]}
    (tmp_path / TRACKS_MANIFEST_FILENAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    items, pre, mode = _resolve_track_pairs(tmp_path, "cover")
    assert mode == "manifest"
    assert len(items) == 0
    assert len(pre) == 1
    assert pre[0][0].name == "s.mp3"


def test_resolve_track_pairs_empty_tracks_json(tmp_path: Path) -> None:
    (tmp_path / TRACKS_MANIFEST_FILENAME).write_text(
        json.dumps({"tracks": []}), encoding="utf-8"
    )
    items, pre, mode = _resolve_track_pairs(tmp_path, "cover")
    assert mode == "manifest"
    assert items == [] and pre == []


def test_batch_encode_duplicate_output_raises(tmp_path: Path) -> None:
    (tmp_path / "cover.png").write_bytes(b"x")
    (tmp_path / "a.mp3").write_bytes(b"\x00")
    (tmp_path / "b.mp3").write_bytes(b"\x00")
    (tmp_path / TRACKS_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "tracks": [
                    {"audio": "a.mp3", "output": "same"},
                    {"audio": "b.mp3", "output": "same"},
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate output name"):
        batch_encode(tmp_path, tmp_path / "out")


def test_resolve_track_pairs_invalid_json_falls_back_to_scan(tmp_path: Path) -> None:
    (tmp_path / TRACKS_MANIFEST_FILENAME).write_text("{ not json", encoding="utf-8")
    (tmp_path / "cover.png").write_bytes(b"x")
    (tmp_path / "a.mp3").write_bytes(b"\x00")
    items, pre, mode = _resolve_track_pairs(tmp_path, "cover")
    assert mode == "scan"
    assert len(items) == 1
    assert items[0].image_path.name == "cover.png"
