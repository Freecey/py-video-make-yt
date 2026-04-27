# video-maker-auto

> Combine a static image + audio file into a YouTube-optimized MP4 video.

Typical use case: publish music clips, podcasts, or tracks on YouTube without video editing software. Just provide a cover image and an audio file — the tool handles encoding.

## Features

- **Single mode** — encode one video from an image + audio file
- **Batch mode** — encode an entire album folder in one command
- **Quality presets** — 1080p, 4K, YouTube Shorts (vertical 9:16), and Shorts 4K
- **Smart image processing** — automatic resize with letterboxing; empty areas filled with a blurred cover-scaled version of the same image (no black bars by default)
- **Audio normalization** — EBU R128 loudness standard for YouTube (`--normalize`)
- **Text overlay** — add title text centered near bottom (`--title`)
- **Thumbnail generation** — 1280x720 JPEG alongside each video (`--thumbnail`)
- **Parallel batch encoding** — multi-threaded batch with `-j/--jobs`
- **Skip existing** — skip already-encoded files (`--skip-existing`)
- **Auto-retry** — retries once with ultrafast preset on failure
- **Config file** — `~/.video-maker.toml` for default settings
- **Dry-run mode** — preview commands without running ffmpeg (`--dry-run`)
- **Disk space check** — verifies free space before batch encoding
- **Progress bar** — visual `[=====>    ] 45%` encoding progress
- **Batch summary** — per-track timing and size table after batch encoding
- **Zero external frameworks** — pure Python + ffmpeg subprocess

## Prerequisites

- Python >= 3.10
- [ffmpeg](https://ffmpeg.org/) installed and in PATH

```bash
# Ubuntu / Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

## Install

```bash
git clone <repo-url> && cd video-maker-auto
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

For development (includes pytest, ruff, mypy, pytest-cov):

```bash
pip install -e ".[dev]"
```

## Quick start

```bash
# One video, default 1080p
python -m video_maker single -i cover.jpg -a track.mp3

# One video in 4K
python -m video_maker single -i cover.jpg -a track.mp3 -q 4k

# YouTube Shorts (vertical 9:16)
python -m video_maker single -i cover.jpg -a track.mp3 -q shorts

# Custom output path
python -m video_maker single -i artwork.png -a podcast.wav -o my_video.mp4

# With audio normalization and text overlay
python -m video_maker single -i cover.jpg -a track.mp3 --normalize --title "My Song"

# Generate a thumbnail too
python -m video_maker single -i cover.jpg -a track.mp3 --thumbnail
```

### Batch — encode a full album

**Default:** put audio files + a `cover.*` image in one folder. **Per-track art:** if an image has the same **stem** as an audio file (e.g. `01-intro.mp3` + `01-intro.png`), that image is used for that track. **Optional `tracks.json`:** if present and valid JSON, the `tracks` list defines each job (per-track `image`, optional `default_cover`, optional `output` filename). See [docs/README.md](docs/README.md) for the full format.

```
my_album/
├── cover.png
├── 01-intro.mp3
├── 02-track.wav
└── 03-outro.flac
```

```bash
# Encode all tracks
python -m video_maker batch my_album/ -q 4k

# Parallel encoding with 4 workers
python -m video_maker batch my_album/ -j 4

# Skip already encoded files
python -m video_maker batch my_album/ --skip-existing

# With normalization and thumbnails
python -m video_maker batch my_album/ --normalize --thumbnail
```

Output in `my_album/output/`:

```
output/
├── 01-intro.mp4
├── 01-intro_thumbnail.jpg   (if --thumbnail)
├── 02-track.mp4
├── 02-track_thumbnail.jpg
├── 03-outro.mp4
└── 03-outro_thumbnail.jpg
```

### Dry-run (preview)

```bash
python -m video_maker --dry-run single -i cover.jpg -a track.mp3
python -m video_maker --dry-run batch my_album/
```

## Configuration

Create `~/.video-maker.toml` to set defaults (CLI flags always override):

```toml
[video-maker]
quality = "4k"
blur_bg = false
normalize = true
title = "My Album"
```

Or use a flat format (without the `[video-maker]` section):

```toml
quality = "4k"
normalize = true
```

## All options

### Global flags

| Flag | Description | Default |
|------|-------------|---------|
| `-v`, `--verbose` | Show debug output (full ffmpeg stderr) | off |
| `--config` | Path to config file | `~/.video-maker.toml` |
| `--dry-run` | Preview commands without running ffmpeg | off |

### Single mode

| Flag | Description | Default |
|------|-------------|---------|
| `-i`, `--image` | Path to image file | required |
| `-a`, `--audio` | Path to audio file | required |
| `-o`, `--output` | Output video path | `<audio_name>.mp4` |
| `-q`, `--quality` | Preset: `1080p`, `4k`, `shorts`, `shorts4k` | `1080p` |
| `--resolution` | Override resolution (`WxH`) | from preset |
| `--bitrate` | Override video bitrate | from preset |
| `--fps` | Override framerate | from preset |
| `--no-blur-bg` | Plain black letterbox instead of blurred background | off (blur on) |
| `--normalize` | Normalize audio (EBU R128 / YouTube standard) | off |
| `--title` | Overlay text (centered, near bottom) | none |
| `--thumbnail` | Generate 1280x720 thumbnail JPEG | off |

### Batch mode

| Flag | Description | Default |
|------|-------------|---------|
| `input_dir` | Folder with audio files | required |
| `-o`, `--output-dir` | Output folder | `<input_dir>/output` |
| `-q`, `--quality` | Preset: `1080p`, `4k`, `shorts`, `shorts4k` | `1080p` |
| `--cover-name` | Cover filename stem | `cover` |
| `--no-blur-bg` | Plain black letterbox | off (blur on) |
| `--skip-existing` | Skip if output is newer than source | off |
| `-j`, `--jobs` | Parallel encoding workers | `1` (sequential) |
| `--normalize` | Normalize audio (EBU R128) | off |
| `--title` | Overlay text on all videos | none |
| `--thumbnail` | Generate thumbnails | off |

## Quality presets

| Preset | Resolution | Aspect | Video bitrate | Framerate |
|--------|-----------|--------|--------------|-----------|
| `1080p` | 1920x1080 | 16:9 landscape | 8 Mbps | 30 fps |
| `4k` | 3840x2160 | 16:9 landscape | 35 Mbps | 30 fps |
| `shorts` | 1080x1920 | 9:16 vertical (YouTube Shorts) | 8 Mbps | 30 fps |
| `shorts4k` | 2160x3840 | 9:16 vertical (YouTube Shorts) | 35 Mbps | 30 fps |

## Output specs (YouTube-optimized)

| Setting | Value |
|---------|-------|
| Container | MP4 |
| Video codec | H.264 High Profile |
| Audio codec | AAC-LC |
| Audio sample rate | 48 kHz stereo |
| Audio bitrate | 384 kbps |
| Pixel format | yuv420p |
| movflags | +faststart |

## Supported formats

- **Image** — jpg, jpeg, png, bmp, webp, tiff
- **Audio** — mp3, wav, aac, m4a, ogg, opus, flac, wma

## Run tests

```bash
# Unit tests
python -m pytest tests/ -v

# Integration tests (requires real ffmpeg)
python -m pytest tests/ -m integration -v

# Coverage report (threshold: 80%)
make test-cov
```

## License

MIT
