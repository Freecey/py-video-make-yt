# Tasks done — video-maker-auto v1.1

## New features
- Added quality presets: `1080p` (1920x1080, 8Mbps) and `4k` (3840x2160, 35Mbps) in `settings.py`
- Added `batch_encode()` in `encoder.py` — processes all audio files in a folder with a shared cover image
- Refactored CLI with subcommands: `single` and `batch` (argparse subparsers)
- CLI flags: `-q/--quality` (1080p|4k), `--resolution`, `--bitrate`, `--fps`, `--cover-name`
- `_prepare_image()` now takes resolution as parameter (no longer hardcoded)

## Documentation
- Created `README.md` (project root) — complete usage guide
- Created `docs/README.md` — user-friendly guide in French
- Created `docs/AGENTS.md` — technical architecture doc for AI agents

## Tests
- Expanded `test_encoder.py`: 20 tests (quality presets, 4K image prep, batch encode, error cases)
- Added `test_cli.py`: 4 tests (arg parsing, single/batch commands, error handling)
- Total: 24/24 tests passing

## Verified
- Integration test 1080p: H.264 High 1920x1080 30fps AAC 48kHz
- Integration test 4K: H.264 High 3840x2160 30fps AAC 48kHz
- Integration test batch: 2 tracks encoded from folder with cover.png
