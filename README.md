# video-maker-auto

> Combine a static image + audio file into a YouTube-optimized MP4 video.

Typical use case: publish music clips, podcasts, or tracks on YouTube without video editing software. Just provide a cover image and an audio file — the tool handles encoding.

## Features

- **Single mode** — encode one video from an image + audio file
- **Batch mode** — encode an entire album folder in one command
- **Quality presets** — 1080p and 4K, YouTube-recommended settings
- **Smart image processing** — automatic resize with letterboxing (no distortion, black bars fill the rest)
- **Override controls** — custom resolution, bitrate, framerate
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
pip install -r requirements.txt
```

For development (includes pytest):

```bash
pip install -e ".[dev]"
```

## Quick start

```bash
# One video, default 1080p
python -m video_maker single -i cover.jpg -a track.mp3

# One video in 4K
python -m video_maker single -i cover.jpg -a track.mp3 -q 4k

# Custom output path
python -m video_maker single -i artwork.png -a podcast.wav -o my_video.mp4
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
python -m video_maker batch my_album/ -q 4k
```

Output in `my_album/output/`:

```
output/
├── 01-intro.mp4
├── 02-track.mp4
└── 03-outro.mp4
```

### All options

| Flag | Description | Default |
|------|-------------|---------|
| `-q`, `--quality` | Preset: `1080p` or `4k` | `1080p` |
| `-o`, `--output` | Output file/folder path | auto |
| `--resolution` | Override resolution (`WxH`) | from preset |
| `--bitrate` | Override video bitrate | from preset |
| `--fps` | Override framerate | from preset |
| `--cover-name` | Cover filename stem (batch only) | `cover` |

## Quality presets

| Preset | Resolution | Video bitrate | Framerate |
|--------|-----------|--------------|-----------|
| `1080p` | 1920x1080 | 8 Mbps | 30 fps |
| `4k` | 3840x2160 | 35 Mbps | 30 fps |

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
source .venv/bin/activate
python -m pytest tests/ -v
```

## License

MIT
