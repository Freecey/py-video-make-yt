"""Core video encoding logic using ffmpeg."""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from video_maker.settings import (
    ENCODING_SETTINGS,
    QUALITY_PRESETS,
    SUPPORTED_AUDIO_EXTENSIONS,
    SUPPORTED_IMAGE_EXTENSIONS,
    QualityPreset,
)


def resolve_quality(quality: str) -> QualityPreset:
    """Return the preset for a given quality label ('1080p' or '4k')."""
    key = quality.lower().strip()
    if key not in QUALITY_PRESETS:
        raise ValueError(
            f"Unknown quality '{quality}'. Available: {', '.join(QUALITY_PRESETS)}"
        )
    return QUALITY_PRESETS[key]


def validate_inputs(image_path: Path, audio_path: Path) -> None:
    """Validate that input files exist and have supported extensions."""
    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    if image_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(
            f"Unsupported image format '{image_path.suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_IMAGE_EXTENSIONS))}"
        )
    if audio_path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
        raise ValueError(
            f"Unsupported audio format '{audio_path.suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}"
        )


def _prepare_image(image_path: Path, work_dir: Path, resolution: tuple[int, int]) -> Path:
    """Resize image to target resolution with letterboxing to preserve aspect ratio."""
    target_w, target_h = resolution
    with Image.open(image_path) as raw_img:
        img = raw_img.convert("RGB")
        if img.size == (target_w, target_h):
            return image_path
        img_ratio = img.width / img.height
        target_ratio = target_w / target_h
        if img_ratio > target_ratio:
            new_w = target_w
            new_h = int(target_w / img_ratio)
        else:
            new_h = target_h
            new_w = int(target_h * img_ratio)
        img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (target_w, target_h), (0, 0, 0))
        offset_x = (target_w - new_w) // 2
        offset_y = (target_h - new_h) // 2
        canvas.paste(img_resized, (offset_x, offset_y))
        prepared_path = work_dir / f"_prepared_{image_path.stem}.png"
        canvas.save(prepared_path, "PNG")
    return prepared_path


def encode_video(
    image_path: Path,
    audio_path: Path,
    output_path: Path,
    quality: str = "1080p",
    resolution: tuple[int, int] | None = None,
    video_bitrate: str | None = None,
    frame_rate: int | None = None,
) -> Path:
    """
    Combine a static image and audio file into an MP4 video optimized for YouTube.

    Returns the path to the generated video.
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is not installed or not in PATH.")

    validate_inputs(image_path, audio_path)

    preset = resolve_quality(quality)

    res = resolution or preset["resolution"]
    vbr = video_bitrate or preset["video_bitrate"]
    fps = frame_rate or preset["frame_rate"]

    output_path = output_path.resolve()

    work_dir = Path(tempfile.mkdtemp(prefix="video_maker_"))

    try:
        prepared_image = _prepare_image(image_path, work_dir, res)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "ffmpeg",
            "-y",
            "-loop", "1",
            "-i", str(prepared_image),
            "-i", str(audio_path),
            "-c:v", ENCODING_SETTINGS["video_codec"],
            "-tune", "stillimage",
            "-preset", ENCODING_SETTINGS["preset"],
            "-profile:v", ENCODING_SETTINGS["profile"],
            "-b:v", vbr,
            "-pix_fmt", ENCODING_SETTINGS["pix_fmt"],
            "-r", str(fps),
            "-c:a", ENCODING_SETTINGS["audio_codec"],
            "-b:a", ENCODING_SETTINGS["audio_bitrate"],
            "-ar", str(ENCODING_SETTINGS["audio_sample_rate"]),
            "-ac", str(ENCODING_SETTINGS["audio_channels"]),
            "-shortest",
            "-movflags", ENCODING_SETTINGS["movflags"],
            str(output_path),
        ]

        print(f"Encoding [{quality.upper()} {res[0]}x{res[1]}]: {output_path.name} ...")
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:
            print(f"ffmpeg stderr:\n{result.stderr}", file=sys.stderr)
            raise RuntimeError(f"ffmpeg failed with exit code {result.returncode}")

        if output_path.exists():
            size_mb = output_path.stat().st_size / (1024 * 1024)
            print(f"Done! Output: {output_path} ({size_mb:.1f} MB)")
        else:
            print(f"Done! Output: {output_path}")

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    return output_path


@dataclasses.dataclass
class BatchResult:
    """Structured result from batch encoding."""
    successes: list[Path]
    failures: list[tuple[Path, str]]


def batch_encode(
    input_dir: Path,
    output_dir: Path,
    quality: str = "1080p",
    image_name: str = "cover",
) -> BatchResult:
    """
    Batch encode all audio files from input_dir using a shared cover image.

    Convention: input_dir must contain audio files and one image file whose stem
    matches `image_name` (default: "cover.*"). Each audio file produces one video.

    Returns a BatchResult with successes and failures.
    """
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {input_dir}")

    image_candidates = [
        f for f in input_dir.iterdir()
        if f.stem.lower() == image_name.lower()
        and f.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ]
    if not image_candidates:
        raise FileNotFoundError(
            f"No cover image named '{image_name}.*' found in {input_dir}. "
            f"Supported: {', '.join(sorted(SUPPORTED_IMAGE_EXTENSIONS))}"
        )
    cover_image = image_candidates[0]

    audio_files = sorted([
        f for f in input_dir.iterdir()
        if f.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
    ])
    if not audio_files:
        raise FileNotFoundError(f"No audio files found in {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    successes: list[Path] = []
    failures: list[tuple[Path, str]] = []

    print(f"Batch mode: {len(audio_files)} audio file(s) with cover '{cover_image.name}'")
    print(f"Quality: {quality} | Output: {output_dir}")
    print("-" * 50)

    for i, audio_file in enumerate(audio_files, 1):
        out_path = output_dir / f"{audio_file.stem}.mp4"
        print(f"\n[{i}/{len(audio_files)}] {audio_file.name}")
        try:
            result = encode_video(
                image_path=cover_image,
                audio_path=audio_file,
                output_path=out_path,
                quality=quality,
            )
            successes.append(result)
        except (RuntimeError, ValueError) as exc:
            print(f"  SKIP: {exc}", file=sys.stderr)
            failures.append((audio_file, str(exc)))

    print("-" * 50)
    print(f"Batch complete: {len(successes)}/{len(audio_files)} video(s) generated.")
    if failures:
        print(f"Failed: {len(failures)} file(s)", file=sys.stderr)
        for failed_path, reason in failures:
            print(f"  - {failed_path.name}: {reason}", file=sys.stderr)

    return BatchResult(successes=successes, failures=failures)
