# Tasks done — audio / encoding review

- **ffmpeg** : added explicit `-map 0:v:0` and `-map 1:a:0` so the first **audio** stream is always used (avoids M4A/MP3/FLAC with embedded cover as MJPEG video stream confusing stream selection).
- **Batch** : `ValueError` if two jobs target the same output filename; CLI catches `ValueError` for batch.
- **Formats** : added `.opus` to `SUPPORTED_AUDIO_EXTENSIONS` and single-mode help.
- **Tests** : assert `-map` in mocked ffmpeg command; new `test_batch_encode_duplicate_output_raises`.
- **Docs** : [docs/AGENTS.md](docs/AGENTS.md) stream-mapping note; [docs/README.md](docs/README.md) audio extensions table.
- **Verification** : 49 pytest tests pass; quick manual encode to `/tmp/vm_test/out.mp4` (h264 + aac).
