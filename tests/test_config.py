"""Tests for video_maker.config module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

from video_maker.config import UserConfig, load_config
from video_maker.cli import main


def test_load_config_missing_file(tmp_path: Path) -> None:
    config = load_config(tmp_path / "nonexistent.toml")
    assert config.quality is None
    assert config.blur_bg is None


def test_load_config_valid_toml(tmp_path: Path) -> None:
    toml_file = tmp_path / ".video-maker.toml"
    toml_file.write_text(
        '[video-maker]\nquality = "4k"\nblur_bg = false\nnormalize = true\n',
        encoding="utf-8",
    )
    config = load_config(toml_file)
    assert config.quality == "4k"
    assert config.blur_bg is False
    assert config.normalize is True


def test_load_config_invalid_toml(tmp_path: Path) -> None:
    toml_file = tmp_path / ".video-maker.toml"
    toml_file.write_text("this is not valid toml {{{{", encoding="utf-8")
    config = load_config(toml_file)
    assert config.quality is None


def test_load_config_custom_path(tmp_path: Path) -> None:
    toml_file = tmp_path / "custom.toml"
    toml_file.write_text(
        '[video-maker]\nquality = "1080p"\ntitle = "Test Title"\n',
        encoding="utf-8",
    )
    config = load_config(toml_file)
    assert config.quality == "1080p"
    assert config.title == "Test Title"


def test_load_config_flat_format(tmp_path: Path) -> None:
    """Config without [video-maker] section should also work."""
    toml_file = tmp_path / ".video-maker.toml"
    toml_file.write_text('quality = "4k"\n', encoding="utf-8")
    config = load_config(toml_file)
    assert config.quality == "4k"


# --- Config applied as CLI defaults ---


def test_config_normalize_applied(tmp_image: Path, tmp_audio: Path, tmp_path: Path) -> None:
    """Config normalize=true must enable normalization even without --normalize flag."""
    config_file = tmp_path / "cfg.toml"
    config_file.write_text('[video-maker]\nnormalize = true\n', encoding="utf-8")
    output = tmp_path / "out.mp4"
    mock_proc = MagicMock()
    mock_proc.stderr = iter([])
    mock_proc.wait.return_value = 0
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_proc) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        main([
            "--config", str(config_file),
            "single",
            "-i", str(tmp_image),
            "-a", str(tmp_audio),
            "-o", str(output),
        ])
    cmd = mock_popen.call_args[0][0]
    assert "-af" in cmd
    assert "loudnorm" in cmd[cmd.index("-af") + 1]


def test_config_title_applied(tmp_image: Path, tmp_audio: Path, tmp_path: Path) -> None:
    """Config title must be used when --title flag is not provided."""
    config_file = tmp_path / "cfg.toml"
    config_file.write_text('[video-maker]\ntitle = "From Config"\n', encoding="utf-8")
    output = tmp_path / "out.mp4"
    mock_proc = MagicMock()
    mock_proc.stderr = iter([])
    mock_proc.wait.return_value = 0
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_proc) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        main([
            "--config", str(config_file),
            "single",
            "-i", str(tmp_image),
            "-a", str(tmp_audio),
            "-o", str(output),
        ])
    cmd = mock_popen.call_args[0][0]
    assert "-vf" in cmd
    assert "From Config" in cmd[cmd.index("-vf") + 1]


def test_config_blur_bg_false_applied(tmp_image: Path, tmp_audio: Path, tmp_path: Path) -> None:
    """Config blur_bg=false must disable blur when --no-blur-bg is not provided."""
    config_file = tmp_path / "cfg.toml"
    config_file.write_text('[video-maker]\nblur_bg = false\n', encoding="utf-8")
    output = tmp_path / "out.mp4"
    mock_proc = MagicMock()
    mock_proc.stderr = iter([])
    mock_proc.wait.return_value = 0
    with patch("video_maker.encoder._prepare_image") as mock_prepare, \
         patch("video_maker.encoder.subprocess.Popen", return_value=mock_proc), \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        mock_prepare.return_value = tmp_image
        main([
            "--config", str(config_file),
            "single",
            "-i", str(tmp_image),
            "-a", str(tmp_audio),
            "-o", str(output),
        ])
    assert mock_prepare.call_args.kwargs.get("blur_bg") is False


def test_cli_flag_overrides_config(tmp_image: Path, tmp_audio: Path, tmp_path: Path) -> None:
    """CLI --normalize flag must take precedence over config normalize=false."""
    config_file = tmp_path / "cfg.toml"
    config_file.write_text('[video-maker]\nnormalize = false\n', encoding="utf-8")
    output = tmp_path / "out.mp4"
    mock_proc = MagicMock()
    mock_proc.stderr = iter([])
    mock_proc.wait.return_value = 0
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_proc) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        main([
            "--config", str(config_file),
            "single",
            "-i", str(tmp_image),
            "-a", str(tmp_audio),
            "-o", str(output),
            "--normalize",
        ])
    cmd = mock_popen.call_args[0][0]
    assert "-af" in cmd


# --- Type validation tests ---


def test_load_config_wrong_type_quality(tmp_path: Path) -> None:
    """Config quality=123 (int) must be ignored."""
    toml_file = tmp_path / "cfg.toml"
    toml_file.write_text("[video-maker]\nquality = 123\n", encoding="utf-8")
    config = load_config(toml_file)
    assert config.quality is None


def test_load_config_wrong_type_blur_bg(tmp_path: Path) -> None:
    """Config blur_bg='yes' (str) must be ignored."""
    toml_file = tmp_path / "cfg.toml"
    toml_file.write_text('[video-maker]\nblur_bg = "yes"\n', encoding="utf-8")
    config = load_config(toml_file)
    assert config.blur_bg is None


def test_load_config_wrong_type_normalize(tmp_path: Path) -> None:
    """Config normalize=1 (int) must be ignored."""
    toml_file = tmp_path / "cfg.toml"
    toml_file.write_text("[video-maker]\nnormalize = 1\n", encoding="utf-8")
    config = load_config(toml_file)
    assert config.normalize is None


def test_config_quality_applied(tmp_image: Path, tmp_audio: Path, tmp_path: Path) -> None:
    """Config quality=4k must be used when -q flag is not provided."""
    config_file = tmp_path / "cfg.toml"
    config_file.write_text('[video-maker]\nquality = "4k"\n', encoding="utf-8")
    output = tmp_path / "out.mp4"
    mock_proc = MagicMock()
    mock_proc.stderr = iter([])
    mock_proc.wait.return_value = 0
    with patch("video_maker.encoder.subprocess.Popen", return_value=mock_proc) as mock_popen, \
         patch("video_maker.encoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        main([
            "--config", str(config_file),
            "single",
            "-i", str(tmp_image),
            "-a", str(tmp_audio),
            "-o", str(output),
        ])
    cmd = mock_popen.call_args[0][0]
    assert "35M" in cmd
