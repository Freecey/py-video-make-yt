# Tasks done — R1 fixes + R2 audit

## R1 Fixes applied
- Replaced `sys.exit(1)` in `encode_video()` with `raise RuntimeError` — proper library behavior
- Removed redundant ffmpeg `-vf` scale/pad filter (Pillow `_prepare_image` already handles resize + letterbox)
- Replaced fixed `_video_maker_tmp` work dir with `tempfile.mkdtemp()` — no collision risk
- Removed unused `ffmpeg-python==0.2.0` dependency from pyproject.toml and requirements.txt
- Aligned Pillow spec: `>=11.0` in both pyproject.toml and requirements.txt
- Added `[project.optional-dependencies] dev = ["pytest>=8.0"]` to pyproject.toml
- `batch_encode()` now returns `BatchResult` dataclass with `successes` and `failures` lists
- CLI `main()` returns exit code 1 when batch has partial failures
- Changed `NotADirectoryError` for non-dir input (was misleading `FileNotFoundError`)
- Removed dead `aspect_ratio` key from `ENCODING_SETTINGS`
- Added `QualityPreset` TypedDict in settings.py; `resolve_quality()` returns typed dict
- Moved `output_path.parent.mkdir()` after `validate_inputs()` in `encode_video()`
- Extracted shared fixtures (`tmp_image`, `tmp_audio`, `batch_dir`, `mock_ffmpeg_ok`, `mock_ffmpeg_fail`) to `tests/conftest.py`
- Expanded CLI tests: 4 → 19 tests (arg defaults, _parse_resolution, batch, no-ffmpeg, overrides, partial failure, help)
- Added `.gitignore` (Python, IDE, OS, project-specific)
- Cleaned unused imports: `ENCODING_SETTINGS` from cli.py and test_encoder.py, `Image` from test_cli.py

## R2 Audit: PASS — no remaining issues

## Test count: 40/40 passing
