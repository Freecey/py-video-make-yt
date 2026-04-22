# Tasks done — R3 audit

## Fixes applied
- Fixed PIL file descriptor leak in `_prepare_image()` — wrapped `Image.open()` in context manager (`with` statement)
- Fixed `batch_encode()` error hierarchy: non-existent path now raises `FileNotFoundError`, non-directory path raises `NotADirectoryError`
- Removed stale `_video_maker_tmp/` entry from `.gitignore` (now using `tempfile.mkdtemp()`)
- Updated `docs/AGENTS.md` to reflect current codebase: removed ffmpeg-python reference, documented BatchResult, error handling, TypedDict, tempfile usage
- Updated `README.md` project structure to include `__main__.py`, `conftest.py`, `.gitignore`

## New tests
- `test_prepare_image_taller_than_16_9` — portrait image letterboxing
- `test_batch_encode_not_a_directory` — file path instead of directory

## Test count: 42/42 passing
