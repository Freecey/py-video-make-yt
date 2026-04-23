"""Tests for video_maker.cli module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from video_maker.cli import main, parse_args, _parse_resolution


# --- parse_args ---

def test_parse_args_single() -> None:
    args = parse_args([
        "single",
        "-i", "cover.jpg",
        "-a", "song.mp3",
        "-q", "4k",
    ])
    assert args.command == "single"
    assert args.quality == "4k"
    assert args.image == Path("cover.jpg")
    assert args.audio == Path("song.mp3")


def test_parse_args_batch() -> None:
    args = parse_args([
        "batch", "/music/album",
        "-q", "4k",
        "--cover-name", "artwork",
    ])
    assert args.command == "batch"
    assert args.quality == "4k"
    assert args.cover_name == "artwork"
    assert args.input_dir == Path("/music/album")


def test_parse_args_single_defaults() -> None:
    args = parse_args(["single", "-i", "img.png", "-a", "audio.wav"])
    assert args.quality == "1080p"
    assert args.output is None
    assert args.resolution is None
    assert args.bitrate is None
    assert args.fps is None


def test_parse_args_batch_defaults() -> None:
    args = parse_args(["batch", "/some/dir"])
    assert args.quality == "1080p"
    assert args.cover_name == "cover"
    assert args.output_dir is None


# --- _parse_resolution ---

def test_parse_resolution_valid() -> None:
    assert _parse_resolution("1920x1080") == (1920, 1080)
    assert _parse_resolution("3840x2160") == (3840, 2160)
    assert _parse_resolution("2560X1440") == (2560, 1440)


def test_parse_resolution_none() -> None:
    assert _parse_resolution(None) is None


def test_parse_resolution_invalid_format() -> None:
    assert _parse_resolution("bad") is None
    assert _parse_resolution("1920") is None
    assert _parse_resolution("1920x1080x5") is None


def test_parse_resolution_non_numeric() -> None:
    assert _parse_resolution("abcxdef") is None


def test_parse_resolution_zero_or_negative() -> None:
    assert _parse_resolution("0x1080") is None
    assert _parse_resolution("1920x0") is None
    assert _parse_resolution("-1920x1080") is None
    assert _parse_resolution("1920x-1080") is None


# --- main: single ---

def test_main_single_success(tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock) -> None:
    with patch("video_maker.encoder.subprocess.run", return_value=mock_ffmpeg_ok), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        ret = main([
            "single",
            "-i", str(tmp_image),
            "-a", str(tmp_audio),
            "-o", str(tmp_path / "out.mp4"),
        ])

    assert ret == 0


def test_main_single_invalid_resolution(tmp_image: Path, tmp_audio: Path) -> None:
    ret = main([
        "single",
        "-i", str(tmp_image),
        "-a", str(tmp_audio),
        "--resolution", "bad",
    ])
    assert ret == 1


def test_main_single_missing_image(tmp_audio: Path, tmp_path: Path) -> None:
    ret = main([
        "single",
        "-i", str(tmp_path / "nonexistent.jpg"),
        "-a", str(tmp_audio),
        "-o", str(tmp_path / "out.mp4"),
    ])
    assert ret == 1


def test_main_single_ffmpeg_fails(tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_fail: MagicMock) -> None:
    with patch("video_maker.encoder.subprocess.run", return_value=mock_ffmpeg_fail), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        ret = main([
            "single",
            "-i", str(tmp_image),
            "-a", str(tmp_audio),
            "-o", str(tmp_path / "out.mp4"),
        ])
    assert ret == 1


def test_main_single_output_parent_is_file(tmp_image: Path, tmp_audio: Path, tmp_path: Path) -> None:
    """main single must return 1 with clean error when output parent path is an existing file."""
    blocker = tmp_path / "notadir"
    blocker.write_text("i am a file")
    with patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        ret = main([
            "single",
            "-i", str(tmp_image),
            "-a", str(tmp_audio),
            "-o", str(blocker / "video.mp4"),
        ])
    assert ret == 1


def test_main_single_no_ffmpeg(tmp_image: Path, tmp_audio: Path, tmp_path: Path) -> None:
    with patch("video_maker.encoder.shutil.which", return_value=None):
        ret = main([
            "single",
            "-i", str(tmp_image),
            "-a", str(tmp_audio),
            "-o", str(tmp_path / "out.mp4"),
        ])
    assert ret == 1


def test_main_single_with_overrides(tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock) -> None:
    with patch("video_maker.encoder.subprocess.run", return_value=mock_ffmpeg_ok) as mock_run, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        ret = main([
            "single",
            "-i", str(tmp_image),
            "-a", str(tmp_audio),
            "-o", str(tmp_path / "out.mp4"),
            "--resolution", "2560x1440",
            "--bitrate", "16M",
            "--fps", "60",
        ])
    assert ret == 0
    cmd = mock_run.call_args[0][0]
    assert "16M" in cmd
    assert "60" in cmd


# --- main: batch ---

def test_main_batch_success(batch_dir: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock) -> None:
    with patch("video_maker.encoder.subprocess.run", return_value=mock_ffmpeg_ok), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        ret = main(["batch", str(batch_dir), "-o", str(tmp_path / "out")])
    assert ret == 0


def test_main_batch_dir_not_found(tmp_path: Path) -> None:
    ret = main(["batch", str(tmp_path / "nonexistent")])
    assert ret == 1


def test_main_batch_no_cover(tmp_path: Path) -> None:
    audio_dir = tmp_path / "no_cover"
    audio_dir.mkdir()
    (audio_dir / "song.mp3").write_bytes(b"\x00")

    ret = main(["batch", str(audio_dir)])
    assert ret == 1


def test_main_batch_partial_failure(batch_dir: Path, tmp_path: Path) -> None:
    """Batch with one failure returns exit code 1."""
    call_count = 0

    def _mock_run(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        result.returncode = 1 if call_count == 1 else 0
        result.stderr = "error" if call_count == 1 else ""
        return result

    with patch("video_maker.encoder.subprocess.run", side_effect=_mock_run), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        ret = main(["batch", str(batch_dir), "-o", str(tmp_path / "out")])
    assert ret == 1


# --- main: no subcommand ---

def test_main_no_command_shows_help(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code == 0
