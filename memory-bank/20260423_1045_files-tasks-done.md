# Audit / Review — 2026-04-23

## Issues found and fixed

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `encoder.py` | `_find_global_cover` + `_find_image_by_stem` iterated the full directory for every audio file (O(n*m)) | Replaced with `_build_image_index()` — single pass, dict lookup |
| 2 | `encoder.py` | Dead branch `if not out_name` after `out_name = f"{ap.stem}.mp4"` | Removed |
| 3 | `encoder.py` | Double `.replace("\\", "/")` — callers and `_file_in_input_dir` both did it | Kept as defense-in-depth; cleaned callers to not pre-strip |
| 4 | `pyproject.toml` | `setuptools.backends._legacy:_Backend` is a deprecated internal backend | Changed to `setuptools.build_meta` |
| 5 | `cli.py` | `parse_args(["--help"])` raises `SystemExit(0)` — the `return 0` after it was unreachable | Removed unreachable `return 0` |

## Verified clean

- No linter errors on all `.py` files
- 49/49 tests passing
- All public imports smoke-tested
- `sys` import confirmed needed (7 usages of `sys.stderr` in encoder)
- `requirements.txt` is clean (only `Pillow>=11.0`)
- Audio formats: .aac, .flac, .m4a, .mp3, .ogg, .opus, .wav, .wma
- Image formats: .bmp, .jpeg, .jpg, .png, .tiff, .webp
- Quality presets: 1080p, 4k
