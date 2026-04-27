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
    assert args.blur_bg is True


def test_parse_args_single_shorts() -> None:
    args = parse_args(["single", "-i", "img.png", "-a", "audio.wav", "-q", "shorts"])
    assert args.quality == "shorts"


def test_parse_args_single_shorts4k() -> None:
    args = parse_args(["single", "-i", "img.png", "-a", "audio.wav", "-q", "shorts4k"])
    assert args.quality == "shorts4k"


def test_parse_args_batch_defaults() -> None:
    args = parse_args(["batch", "/some/dir"])
    assert args.quality == "1080p"
    assert args.cover_name == "cover"
    assert args.output_dir is None
    assert args.blur_bg is True
    assert args.skip_existing is False


def test_parse_args_batch_shorts() -> None:
    args = parse_args(["batch", "/some/dir", "-q", "shorts"])
    assert args.quality == "shorts"


def test_parse_args_batch_skip_existing() -> None:
    args = parse_args(["batch", "/some/dir", "--skip-existing"])
    assert args.skip_existing is True


def test_parse_args_batch_jobs() -> None:
    args = parse_args(["batch", "/some/dir", "-j", "4"])
    assert args.jobs == 4


def test_parse_args_batch_jobs_default() -> None:
    args = parse_args(["batch", "/some/dir"])
    assert args.jobs == 1


def test_parse_args_single_no_blur_bg() -> None:
    """--no-blur-bg on single sets blur_bg to False."""
    args = parse_args(["single", "-i", "img.png", "-a", "audio.wav", "--no-blur-bg"])
    assert args.blur_bg is False


def test_parse_args_batch_no_blur_bg() -> None:
    """--no-blur-bg on batch sets blur_bg to False."""
    args = parse_args(["batch", "/some/dir", "--no-blur-bg"])
    assert args.blur_bg is False


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
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok), \
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
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_fail), \
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
    with patch("video_maker.encoder.check_ffmpeg_available", side_effect=RuntimeError("ffmpeg is not installed or not in PATH.")):
        ret = main([
            "single",
            "-i", str(tmp_image),
            "-a", str(tmp_audio),
            "-o", str(tmp_path / "out.mp4"),
        ])
    assert ret == 1


def test_main_single_with_overrides(tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock) -> None:
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok) as mock_run, \
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
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok), \
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

    def _mock_popen(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        process = MagicMock()
        # Fail the first AND second call (normal + retry) for track 1
        if call_count <= 2:
            process.stderr = iter(["error\n"])
            process.wait.return_value = 1
        else:
            process.stderr = iter([])
            process.wait.return_value = 0
        return process

    with patch("video_maker.encoder.subprocess.Popen", side_effect=_mock_popen), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        ret = main(["batch", str(batch_dir), "-o", str(tmp_path / "out")])
    assert ret == 1


def test_main_single_no_blur_bg_propagates(
    tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """main single must pass blur_bg=False to _prepare_image when --no-blur-bg is used."""
    with patch("video_maker.encoder._prepare_image") as mock_prepare, \
         patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        mock_prepare.return_value = tmp_image
        ret = main([
            "single",
            "-i", str(tmp_image),
            "-a", str(tmp_audio),
            "-o", str(tmp_path / "out.mp4"),
            "--no-blur-bg",
        ])
    assert ret == 0
    assert mock_prepare.call_args.kwargs.get("blur_bg") is False


def test_main_single_shorts(
    tmp_image: Path, tmp_audio: Path, tmp_path: Path, mock_ffmpeg_ok: MagicMock
) -> None:
    """main single with -q shorts must encode with shorts bitrate."""
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_ffmpeg_ok) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        ret = main([
            "single",
            "-i", str(tmp_image),
            "-a", str(tmp_audio),
            "-o", str(tmp_path / "out.mp4"),
            "-q", "shorts",
        ])
    assert ret == 0
    cmd = mock_popen.call_args[0][0]
    assert "8M" in cmd


# --- main: no subcommand ---

def test_main_no_command_shows_help(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code == 0
