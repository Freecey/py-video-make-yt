# Tasks done — batch multi-image pairing (tracks.json + name match + cover)

- Added `TrackItem` dataclass; `settings.TRACKS_MANIFEST_FILENAME` (`tracks.json`)
- Implemented `_resolve_track_pairs()`: manifest mode (valid JSON + non-empty `tracks`), or folder scan; image resolution order: per-track `image` > `default_cover` > same-stem image > global `cover.*` (`--cover-name`)
- Refactored `batch_encode()` to use job list, pre-failures (no image), combined `encode_failures`; fixed `_file_in_input_dir` path security
- Updated CLI `batch` subparser help text
- Tests: `test_batch_encode_no_cover` now expects `BatchResult` with failures; added 6 tests for `_resolve_track_pairs`
- Doc: [docs/README.md](docs/README.md) (user FR), [docs/AGENTS.md](docs/AGENTS.md), [README.md](README.md) batch section
- All 48 tests passing
