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
    _parse_ffmpeg_error,
    _format_progress_bar,
    check_ffmpeg_available,
    _resolve_track_pairs,
    encode_video,
    batch_encode,
    resolve_quality,
    BatchResult,
    TrackResult,
)
from video_maker.settings import TRACKS_MANIFEST_FILENAME
from video_maker.settings import QUALITY_PRESETS


# --- resolve_quality ---

def test_resolve_quality_1080p() -> None:
    preset = resolve_quality("1080p")
    assert preset.resolution == (1920, 1080)
    assert preset.video_bitrate == "8M"


def test_resolve_quality_4k() -> None:
    preset = resolve_quality("4k")
    assert preset.resolution == (3840, 2160)
    assert preset.video_bitrate == "35M"


def test_resolve_quality_invalid() -> None:
    with pytest.raises(ValueError, match="Unknown quality"):
        resolve_quality("720p")


def test_resolve_quality_case_insensitive() -> None:
    assert resolve_quality("1080P").resolution == (1920, 1080)
    assert resolve_quality("4K").resolution == (3840, 2160)


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
    w, h = QUALITY_PRESETS["1080p"].resolution
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


def test_prepare_image_blur_bg_default_fills_background(tmp_path: Path) -> None:
    """blur_bg=True (default): letterbox areas must be filled with blurred image, not black."""
    # Square green image on 16:9 canvas → letterbox on left and right sides.
    img = Image.new("RGB", (400, 400), (0, 200, 0))
    path = tmp_path / "green_square.png"
    img.save(path)
    result = _prepare_image(path, tmp_path, (1920, 1080), blur_bg=True)
    prepared = Image.open(result)
    assert prepared.size == (1920, 1080)
    # Pixel at (0, 0) is in the left letterbox zone (foreground starts at x=420).
    # With blurred green background it must NOT be pure black.
    r, g, b = prepared.getpixel((0, 0))
    assert (r, g, b) != (0, 0, 0), "blur_bg=True must not produce pure-black letterbox bars"
    assert g > r and g > b, "Blurred green background should keep green channel dominant"


def test_prepare_image_no_blur_bg_uses_black_letterbox(tmp_path: Path) -> None:
    """blur_bg=False: letterbox areas must be plain black (classic behavior)."""
    img = Image.new("RGB", (400, 400), (0, 200, 0))
    path = tmp_path / "green_square.png"
    img.save(path)
    result = _prepare_image(path, tmp_path, (1920, 1080), blur_bg=False)
    prepared = Image.open(result)
    assert prepared.size == (1920, 1080)
    # (0, 0) is in the left letterbox → must be pure black
    assert prepared.getpixel((0, 0)) == (0, 0, 0)


def test_prepare_image_already_correct_size_unaffected_by_blur_bg(tmp_path: Path) -> None:
    """Image already at exact canvas size: blur_bg has no effect, returns original path."""
    w, h = 1920, 1080
    img = Image.new("RGB", (w, h), (0, 128, 255))
    path = tmp_path / "exact.png"
    img.save(path)
    assert _prepare_image(path, tmp_path, (w, h), blur_bg=True) == path
    assert _prepare_image(path, tmp_path, (w, h), blur_bg=False) == path


def test_encode_video_passes_blur_bg_false(
    tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """encode_video must forward blur_bg=False to _prepare_image."""
    output = tmp_path / "output.mp4"
    with patch("video_maker.encoder._prepare_image") as mock_prepare, \
         patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        mock_prepare.return_value = tmp_image
        encode_video(tmp_image, tmp_audio, output, blur_bg=False)
    mock_prepare.assert_called_once()
    assert mock_prepare.call_args.kwargs.get("blur_bg") is False


# --- encode_video ---

def test_encode_video_success(tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock) -> None:
    output = tmp_path / "output.mp4"

    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        output_path = encode_video(tmp_image, tmp_audio, output)

    assert output_path == output.resolve()
    mock_popen.assert_called_once()

    cmd = mock_popen.call_args[0][0]
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

    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        encode_video(tmp_image, tmp_audio, output, quality="4k")

    cmd = mock_popen.call_args[0][0]
    assert "35M" in cmd


def test_encode_video_ffmpeg_fails(tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_fail: MagicMock) -> None:
    output = tmp_path / "fail.mp4"

    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_fail), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            encode_video(tmp_image, tmp_audio, output)


def test_encode_video_no_ffmpeg(tmp_image: Path, tmp_audio: Path, tmp_path: Path) -> None:
    output = tmp_path / "nope.mp4"

    with patch("video_maker.encoder.check_ffmpeg_available", side_effect=RuntimeError("ffmpeg is not installed or not in PATH.")):
        with pytest.raises(RuntimeError, match="ffmpeg is not installed"):
            encode_video(tmp_image, tmp_audio, output)


def test_encode_video_output_parent_is_file(tmp_image: Path, tmp_audio: Path, tmp_path: Path) -> None:
    """encode_video must raise NotADirectoryError if the output parent is an existing file."""
    blocker = tmp_path / "notadir"
    blocker.write_text("i am a file")
    output = blocker / "video.mp4"
    with patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        with pytest.raises(NotADirectoryError, match="already exists as a file"):
            encode_video(tmp_image, tmp_audio, output)


# --- batch_encode ---

def test_batch_encode_success(batch_dir: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock) -> None:
    output_dir = tmp_path / "videos_out"

    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok), \
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


def test_batch_encode_output_dir_is_existing_file(batch_dir: Path, tmp_path: Path) -> None:
    existing_file = tmp_path / "output"
    existing_file.write_text("i am a file, not a directory")
    with pytest.raises(NotADirectoryError, match="already exists as a file"):
        batch_encode(batch_dir, existing_file)


def test_batch_encode_partial_failure(batch_dir: Path, tmp_path: Path) -> None:
    """Test that batch_encode returns structured result when some files fail."""
    output_dir = tmp_path / "partial_out"
    call_count = 0

    def _mock_popen(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        process = MagicMock()
        if call_count == 2:
            process.stderr = iter(["Error: encode error\n"])
            process.wait.return_value = 1
        else:
            process.stderr = iter([])
            process.wait.return_value = 0
        return process

    with patch("video_maker.encoder.subprocess.Popen", side_effect=_mock_popen), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        result = batch_encode(batch_dir, output_dir, quality="1080p", retry=False)

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


def test_resolve_track_pairs_non_dict_json_falls_back_to_scan(tmp_path: Path) -> None:
    """Valid JSON that is not an object (e.g. an array) must warn and fall back to scan."""
    (tmp_path / TRACKS_MANIFEST_FILENAME).write_text(
        json.dumps([{"audio": "a.mp3"}]), encoding="utf-8"
    )
    (tmp_path / "cover.png").write_bytes(b"x")
    (tmp_path / "a.mp3").write_bytes(b"\x00")
    items, pre, mode = _resolve_track_pairs(tmp_path, "cover")
    assert mode == "scan"
    assert len(items) == 1
    assert items[0].image_path.name == "cover.png"


def test_resolve_track_pairs_dict_without_tracks_key_falls_back_to_scan(tmp_path: Path) -> None:
    """tracks.json that is a valid dict but has no 'tracks' key falls back silently to scan.

    In this case _load_tracks_manifest returns the dict, but _resolve_track_pairs
    sees manifest.get('tracks') is None (not a list) and takes the scan path.
    No warning is emitted. Any 'default_cover' defined in that manifest is ignored.
    """
    (tmp_path / TRACKS_MANIFEST_FILENAME).write_text(
        json.dumps({"default_cover": "art.png"}), encoding="utf-8"
    )
    img = Image.new("RGB", (10, 10))
    img.save(tmp_path / "cover.png")
    (tmp_path / "a.mp3").write_bytes(b"\x00")
    items, pre, mode = _resolve_track_pairs(tmp_path, "cover")
    assert mode == "scan"
    assert len(items) == 1
    # default_cover from the manifest is NOT used in scan mode;
    # cover.png is found via the image_index / global_cover path
    assert items[0].image_path.name == "cover.png"


# --- _parse_ffmpeg_error ---


def test_parse_ffmpeg_error_extracts_error_lines() -> None:
    stderr = (
        "ffmpeg version 6.0\n"
        "Input #0, mp3, from 'song.mp3'\n"
        "[error] Error while decoding stream #0:0\n"
        "Conversion failed!\n"
    )
    result = _parse_ffmpeg_error(stderr)
    assert "Error while decoding stream" in result
    assert "Conversion failed!" in result
    assert "ffmpeg version" not in result


def test_parse_ffmpeg_error_empty_stderr() -> None:
    assert "no stderr output" in _parse_ffmpeg_error("")


def test_parse_ffmpeg_error_no_error_markers() -> None:
    result = _parse_ffmpeg_error("line1\nline2\nline3\nline4\n")
    assert "line4" in result


def test_parse_ffmpeg_error_none_stderr() -> None:
    assert "no stderr output" in _parse_ffmpeg_error(None)


# --- check_ffmpeg_available ---


def test_check_ffmpeg_available_success() -> None:
    encoders_output = (
        " ---------------------\n"
        " V..... libx264       libx264 H.264\n"
        " A..... aac           AAC (Advanced Audio Coding)\n"
    )
    mock_result = MagicMock()
    mock_result.stdout = encoders_output
    check_ffmpeg_available.cache_clear()
    with patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("video_maker.encoder.subprocess.run", return_value=mock_result):
        path = check_ffmpeg_available()
    assert path == "/usr/bin/ffmpeg"


def test_check_ffmpeg_available_not_installed() -> None:
    check_ffmpeg_available.cache_clear()
    with patch("video_maker.encoder.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="ffmpeg is not installed"):
            check_ffmpeg_available()


def test_check_ffmpeg_available_missing_codecs() -> None:
    mock_result = MagicMock()
    mock_result.stdout = " V..... flv           FLV\n"
    check_ffmpeg_available.cache_clear()
    with patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("video_maker.encoder.subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError, match="missing required codecs"):
            check_ffmpeg_available()


def test_check_ffmpeg_available_cached() -> None:
    encoders_output = " V..... libx264       libx264\n A..... aac           AAC\n"
    mock_result = MagicMock()
    mock_result.stdout = encoders_output
    check_ffmpeg_available.cache_clear()
    with patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg") as mock_which, \
         patch("video_maker.encoder.subprocess.run", return_value=mock_result) as mock_run:
        check_ffmpeg_available()
        check_ffmpeg_available()
    assert mock_run.call_count == 1


# --- dry_run ---


def test_encode_video_dry_run_no_subprocess(
    tmp_image: Path, tmp_audio: Path, tmp_path: Path
) -> None:
    output = tmp_path / "output.mp4"
    with patch("video_maker.encoder.subprocess.Popen") as mock_popen:
        result = encode_video(tmp_image, tmp_audio, output, dry_run=True)
    mock_popen.assert_not_called()
    assert result == output.resolve()


def test_batch_encode_dry_run(batch_dir: Path, tmp_path: Path) -> None:
    output_dir = tmp_path / "dry_out"
    with patch("video_maker.encoder.subprocess.Popen") as mock_popen:
        result = batch_encode(batch_dir, output_dir, dry_run=True)
    mock_popen.assert_not_called()
    assert len(result.successes) == 3
    assert len(result.failures) == 0


# --- skip_existing ---


def test_batch_encode_skip_existing_skips_newer_output(
    batch_dir: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """Output already exists and is newer than audio: skip without calling ffmpeg."""
    output_dir = tmp_path / "skip_out"
    output_dir.mkdir()

    # Create pre-existing output files that are newer than audio sources
    for audio in sorted(batch_dir.iterdir()):
        if audio.suffix.lower() in {".mp3", ".wav", ".flac"}:
            out_file = output_dir / f"{audio.stem}.mp4"
            out_file.write_bytes(b"fake mp4")
            # Ensure output mtime > audio mtime
            import os
            audio_mtime = audio.stat().st_mtime
            os.utime(out_file, (audio_mtime + 100, audio_mtime + 100))

    with patch("video_maker.encoder.subprocess.Popen") as mock_popen:
        result = batch_encode(batch_dir, output_dir, skip_existing=True)

    mock_popen.assert_not_called()
    assert len(result.successes) == 3
    assert len(result.failures) == 0


def test_batch_encode_skip_existing_re_encodes_older_output(
    batch_dir: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """Output exists but is older than audio: must re-encode."""
    output_dir = tmp_path / "stale_out"
    output_dir.mkdir()

    # Create stale output files (older than audio)
    for audio in sorted(batch_dir.iterdir()):
        if audio.suffix.lower() in {".mp3", ".wav", ".flac"}:
            out_file = output_dir / f"{audio.stem}.mp4"
            out_file.write_bytes(b"stale mp4")
            import os
            audio_mtime = audio.stat().st_mtime
            os.utime(out_file, (audio_mtime - 100, audio_mtime - 100))

    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        result = batch_encode(batch_dir, output_dir, skip_existing=True)

    assert mock_popen.call_count == 3
    assert len(result.successes) == 3
    assert len(result.failures) == 0


def test_batch_encode_skip_existing_false_does_not_skip(
    batch_dir: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """skip_existing=False (default): re-encode even if output is newer."""
    output_dir = tmp_path / "noskip_out"
    output_dir.mkdir()

    for audio in sorted(batch_dir.iterdir()):
        if audio.suffix.lower() in {".mp3", ".wav", ".flac"}:
            out_file = output_dir / f"{audio.stem}.mp4"
            out_file.write_bytes(b"existing mp4")
            import os
            audio_mtime = audio.stat().st_mtime
            os.utime(out_file, (audio_mtime + 100, audio_mtime + 100))

    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        result = batch_encode(batch_dir, output_dir, skip_existing=False)

    assert mock_popen.call_count == 3
    assert len(result.successes) == 3


# --- parallel encoding ---


def test_batch_encode_parallel_workers(
    batch_dir: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """max_workers=2 uses ThreadPoolExecutor and still produces correct results."""
    output_dir = tmp_path / "parallel_out"
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        result = batch_encode(batch_dir, output_dir, max_workers=2)

    assert mock_popen.call_count == 3
    assert len(result.successes) == 3
    assert len(result.failures) == 0


def test_batch_encode_parallel_partial_failure(
    batch_dir: Path, tmp_path: Path
) -> None:
    """Parallel batch with one failure still collects results correctly."""
    output_dir = tmp_path / "par_partial"
    call_count = 0

    def _mock_popen(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        process = MagicMock()
        if call_count == 2:
            process.stderr = iter(["Error: encode error\n"])
            process.wait.return_value = 1
        else:
            process.stderr = iter([])
            process.wait.return_value = 0
        return process

    with patch("video_maker.encoder.subprocess.Popen", side_effect=_mock_popen), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        result = batch_encode(batch_dir, output_dir, max_workers=2, retry=False)

    assert len(result.successes) == 2
    assert len(result.failures) == 1


# --- normalize ---


def test_encode_video_normalize_adds_loudnorm(
    tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """normalize=True must inject -af loudnorm into the ffmpeg command."""
    output = tmp_path / "normalized.mp4"
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        encode_video(tmp_image, tmp_audio, output, normalize=True)

    cmd = mock_popen.call_args[0][0]
    af_idx = cmd.index("-af")
    loudnorm_filter = cmd[af_idx + 1]
    assert "loudnorm" in loudnorm_filter
    assert "I=-14" in loudnorm_filter
    assert "TP=-1" in loudnorm_filter
    assert "LRA=11" in loudnorm_filter


def test_encode_video_no_normalize_omits_af(
    tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """normalize=False (default) must NOT include -af in the ffmpeg command."""
    output = tmp_path / "plain.mp4"
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        encode_video(tmp_image, tmp_audio, output, normalize=False)

    cmd = mock_popen.call_args[0][0]
    assert "-af" not in cmd


def test_batch_encode_normalize_propagates(
    batch_dir: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """batch_encode with normalize=True must pass it to each encode_video call."""
    output_dir = tmp_path / "norm_out"
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        batch_encode(batch_dir, output_dir, normalize=True)

    assert mock_popen.call_count == 3
    for call in mock_popen.call_args_list:
        cmd = call[0][0]
        assert "-af" in cmd
        af_idx = cmd.index("-af")
        assert "loudnorm" in cmd[af_idx + 1]


# --- title overlay ---


def test_encode_video_title_adds_drawtext(
    tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """title="My Song" must inject -vf drawtext into the ffmpeg command."""
    output = tmp_path / "titled.mp4"
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        encode_video(tmp_image, tmp_audio, output, title="My Song")

    cmd = mock_popen.call_args[0][0]
    vf_idx = cmd.index("-vf")
    drawtext = cmd[vf_idx + 1]
    assert "drawtext" in drawtext
    assert "My Song" in drawtext
    assert "fontsize=36" in drawtext
    assert "fontcolor=white" in drawtext
    assert "x=(w-text_w)/2" in drawtext


def test_encode_video_no_title_omits_vf(
    tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """title=None (default) must NOT include -vf in the ffmpeg command."""
    output = tmp_path / "notitle.mp4"
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        encode_video(tmp_image, tmp_audio, output)

    cmd = mock_popen.call_args[0][0]
    assert "-vf" not in cmd


def test_encode_video_title_escapes_special_chars(
    tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """title with special chars (:, ', %) must be escaped."""
    output = tmp_path / "escaped.mp4"
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        encode_video(tmp_image, tmp_audio, output, title="It's 100%: Test")

    cmd = mock_popen.call_args[0][0]
    vf_idx = cmd.index("-vf")
    drawtext = cmd[vf_idx + 1]
    assert "drawtext" in drawtext
    # Escaped chars should be present (backslash-escaped)
    assert "\\'" in drawtext  # escaped single quote
    assert "\\\\:" in drawtext  # escaped colon


def test_batch_encode_title_propagates(
    batch_dir: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """batch_encode with title must pass it to each encode_video call."""
    output_dir = tmp_path / "title_out"
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        batch_encode(batch_dir, output_dir, title="Album Title")

    assert mock_popen.call_count == 3
    for call in mock_popen.call_args_list:
        cmd = call[0][0]
        assert "-vf" in cmd
        assert "Album Title" in cmd[cmd.index("-vf") + 1]


# --- thumbnail ---


def test_encode_video_generate_thumbnail(
    tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """generate_thumbnail=True must create a _thumbnail.jpg next to the output."""
    output = tmp_path / "thumb_test.mp4"
    # Create a fake output file so the "exists" check passes
    output.write_bytes(b"fake mp4")

    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        encode_video(tmp_image, tmp_audio, output, generate_thumbnail=True)

    thumb_path = tmp_path / "thumb_test_thumbnail.jpg"
    assert thumb_path.exists()
    thumb = Image.open(thumb_path)
    assert thumb.size == (1280, 720)


def test_encode_video_no_thumbnail_by_default(
    tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """generate_thumbnail=False (default) must NOT create a thumbnail."""
    output = tmp_path / "nothumb.mp4"
    output.write_bytes(b"fake mp4")

    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        encode_video(tmp_image, tmp_audio, output)

    thumb_path = tmp_path / "nothumb_thumbnail.jpg"
    assert not thumb_path.exists()


# --- retry ---


def test_encode_video_preset_override(
    tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """_preset_override must replace the default preset in the ffmpeg command."""
    output = tmp_path / "preset.mp4"
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        encode_video(tmp_image, tmp_audio, output, _preset_override="ultrafast")

    cmd = mock_popen.call_args[0][0]
    preset_idx = cmd.index("-preset")
    assert cmd[preset_idx + 1] == "ultrafast"


def test_batch_encode_retry_success_on_second_attempt(
    batch_dir: Path, tmp_path: Path
) -> None:
    """First attempt fails, retry with ultrafast succeeds."""
    output_dir = tmp_path / "retry_out"
    call_count = 0

    def _mock_popen(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        process = MagicMock()
        # First call (normal preset) fails
        if call_count == 1:
            process.stderr = iter(["Error: something\n"])
            process.wait.return_value = 1
        else:
            # Retry with ultrafast succeeds
            process.stderr = iter([])
            process.wait.return_value = 0
        return process

    with patch("video_maker.encoder.subprocess.Popen", side_effect=_mock_popen), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        result = batch_encode(batch_dir, output_dir)

    # All 3 tracks should succeed (1st track retries and succeeds)
    assert len(result.successes) >= 1
    assert len(result.failures) == 0


def test_batch_encode_retry_disabled(
    batch_dir: Path, tmp_path: Path
) -> None:
    """retry=False: no retry, failure reported immediately."""
    output_dir = tmp_path / "noretry_out"

    def _mock_popen(*args, **kwargs):
        process = MagicMock()
        process.stderr = iter(["Error: fail\n"])
        process.wait.return_value = 1
        return process

    with patch("video_maker.encoder.subprocess.Popen", side_effect=_mock_popen), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        result = batch_encode(batch_dir, output_dir, retry=False)

    assert len(result.successes) == 0
    assert len(result.failures) == 3


# --- disk space check ---


def test_batch_encode_insufficient_disk_space(
    batch_dir: Path, tmp_path: Path
) -> None:
    """Must raise OSError when disk space is insufficient."""
    output_dir = tmp_path / "nospace_out"
    output_dir.mkdir()

    # Mock disk_usage to report very low free space
    mock_usage = MagicMock()
    mock_usage.free = 100  # 100 bytes — way too low
    with patch("video_maker.encoder.shutil.disk_usage", return_value=mock_usage):
        with pytest.raises(OSError, match="Insufficient disk space"):
            batch_encode(batch_dir, output_dir)


def test_batch_encode_sufficient_disk_space(
    batch_dir: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """Must proceed normally when disk space is sufficient."""
    output_dir = tmp_path / "space_ok"
    output_dir.mkdir()

    mock_usage = MagicMock()
    mock_usage.free = 100 * 1024 ** 3  # 100 GB — plenty
    with patch("video_maker.encoder.shutil.disk_usage", return_value=mock_usage), \
         patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        result = batch_encode(batch_dir, output_dir)

    assert len(result.successes) == 3


def test_batch_encode_dry_run_skips_disk_check(
    batch_dir: Path, tmp_path: Path
) -> None:
    """dry_run=True must skip the disk space check."""
    output_dir = tmp_path / "dry_nospace"
    output_dir.mkdir()

    mock_usage = MagicMock()
    mock_usage.free = 100  # 100 bytes — too low but dry_run should skip
    with patch("video_maker.encoder.shutil.disk_usage", return_value=mock_usage):
        result = batch_encode(batch_dir, output_dir, dry_run=True)

    assert len(result.successes) == 3


# --- progress bar ---


def test_format_progress_bar_zero() -> None:
    bar = _format_progress_bar(0.0, 100.0)
    assert "[>" in bar
    assert "0.0%" in bar
    assert "(00:00 / 01:40)" in bar


def test_format_progress_bar_half() -> None:
    bar = _format_progress_bar(50.0, 100.0)
    assert "50.0%" in bar
    assert "=" in bar


def test_format_progress_bar_full() -> None:
    bar = _format_progress_bar(100.0, 100.0)
    assert "100.0%" in bar


def test_format_progress_bar_no_total() -> None:
    bar = _format_progress_bar(45.0, 0.0)
    assert "00:45" in bar


# --- TrackResult & batch summary ---


def test_track_result_size_mb() -> None:
    tr = TrackResult(name="test.mp4", status="ok", elapsed=5.0, size_bytes=1024 * 1024 * 2)
    assert tr.size_mb == 2.0


def test_track_result_size_mb_zero() -> None:
    tr = TrackResult(name="fail.mp4", status="failed", elapsed=0.0, size_bytes=0)
    assert tr.size_mb == 0.0


def test_batch_encode_populates_track_results(
    batch_dir: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """batch_encode must populate track_results with timing info."""
    output_dir = tmp_path / "summary_out"
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        result = batch_encode(batch_dir, output_dir)

    assert len(result.track_results) == 3
    for tr in result.track_results:
        assert tr.status == "ok"
        assert tr.name.endswith(".mp4")


def test_batch_encode_track_results_includes_failures(
    batch_dir: Path, tmp_path: Path
) -> None:
    """Failed tracks must appear in track_results with status='failed'."""
    output_dir = tmp_path / "fail_summary"

    def _mock_popen(*args, **kwargs):
        process = MagicMock()
        process.stderr = iter(["Error: fail\n"])
        process.wait.return_value = 1
        return process

    with patch("video_maker.encoder.subprocess.Popen", side_effect=_mock_popen), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        result = batch_encode(batch_dir, output_dir, retry=False)

    assert len(result.track_results) == 3
    assert all(tr.status == "failed" for tr in result.track_results)


# --- Audit fix tests ---


def test_escape_drawtext_curly_braces_and_semicolon() -> None:
    """drawtext must escape {}, ;, newlines."""
    from video_maker.encoder import _escape_drawtext
    result = _escape_drawtext("test{ok};done\nmore\r")
    assert "\\\\{" in result
    assert "\\\\}" in result
    assert "\\\\;" in result
    assert "\n" not in result
    assert "\r" not in result


def test_normalize_output_name_rejects_path_traversal() -> None:
    """_normalize_output_name must reject ../ in output names."""
    from video_maker.encoder import _normalize_output_name
    assert _normalize_output_name("../../../tmp/evil") == ""
    assert _normalize_output_name("sub/file") == ""
    assert _normalize_output_name("normal") == "normal.mp4"


def test_skip_existing_ignores_zero_byte_file(
    batch_dir: Path, tmp_path: Path
) -> None:
    """skip_existing must NOT skip 0-byte output files."""
    output_dir = tmp_path / "zero_byte"
    output_dir.mkdir()
    # Create a 0-byte output file that is newer than the audio
    for audio in batch_dir.iterdir():
        if audio.suffix == ".mp3":
            zero_file = output_dir / f"{audio.stem}.mp4"
            zero_file.touch()
            break

    mock_proc = MagicMock()
    mock_proc.stderr = iter([])
    mock_proc.wait.return_value = 0

    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_proc) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        result = batch_encode(batch_dir, output_dir, skip_existing=True, retry=False)

    # The 0-byte file should NOT have been skipped — ffmpeg was called
    assert mock_popen.called
    assert len(result.successes) >= 1


def test_parallel_mode_populates_skipped(
    batch_dir: Path, tmp_path: Path
) -> None:
    """Parallel mode must populate skipped tracks correctly."""
    output_dir = tmp_path / "parallel_skip"
    output_dir.mkdir()
    # Pre-create valid output files (non-zero, newer than audio)
    for audio in batch_dir.iterdir():
        if audio.suffix in (".mp3", ".wav", ".flac"):
            out = output_dir / f"{audio.stem}.mp4"
            out.write_bytes(b"fake mp4 data")

    mock_proc = MagicMock()
    mock_proc.stderr = iter([])
    mock_proc.wait.return_value = 0

    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_proc), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        result = batch_encode(
            batch_dir, output_dir, skip_existing=True, max_workers=2
        )

    assert len(result.successes) == 3
    skipped_results = [tr for tr in result.track_results if tr.status == "skipped"]
    assert len(skipped_results) == 3
