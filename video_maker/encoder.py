"""Core video encoding logic using ffmpeg."""

from __future__ import annotations

import dataclasses
import functools
import json
import logging
import re
from collections import Counter
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageFilter, UnidentifiedImageError

from video_maker.settings import (
    BLUR_BACKGROUND_RADIUS,
    ENCODING_SETTINGS,
    LOUDNORM_TARGET_I,
    LOUDNORM_TARGET_LRA,
    LOUDNORM_TARGET_TP,
    QUALITY_PRESETS,
    SUPPORTED_AUDIO_EXTENSIONS,
    SUPPORTED_IMAGE_EXTENSIONS,
    TEXT_OVERLAY_BORDER_COLOR,
    TEXT_OVERLAY_BORDER_WIDTH,
    TEXT_OVERLAY_FONT_COLOR,
    TEXT_OVERLAY_FONT_SIZE,
    TEXT_OVERLAY_Y_OFFSET,
    THUMBNAIL_FORMAT,
    THUMBNAIL_SIZE,
    THUMBNAIL_SUFFIX,
    TRACKS_MANIFEST_FILENAME,
    EncodingSettings,
    QualityPreset,
)

logger = logging.getLogger(__name__)

_ERROR_MARKERS = ("[error]", "error:", "invalid", "cannot", "no such", "not found", "failed")

_REQUIRED_CODECS = {"libx264", "aac"}


@functools.lru_cache(maxsize=1)
def check_ffmpeg_available() -> str:
    """Check ffmpeg is installed and has required codecs.

    Returns the ffmpeg path. Raises RuntimeError if missing or codecs unavailable.
    """
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise RuntimeError("ffmpeg is not installed or not in PATH.")
    try:
        result = subprocess.run(
            ["ffmpeg", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise RuntimeError(f"Cannot query ffmpeg encoders: {exc}") from exc
    found = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith((" ", "V", "A")):
            found.add(parts[1].lstrip("."))
    missing = _REQUIRED_CODECS - found
    if missing:
        raise RuntimeError(
            f"ffmpeg missing required codecs: {', '.join(sorted(missing))}"
        )
    return ffmpeg_path


def _parse_ffmpeg_error(stderr: str | None) -> str:
    """Extract the last meaningful error lines from ffmpeg stderr."""
    if not stderr:
        return "ffmpeg failed (no stderr output)"
    lines = stderr.strip().splitlines()
    error_lines: list[str] = []
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if any(marker in lower for marker in _ERROR_MARKERS):
            error_lines.append(stripped)
        if len(error_lines) >= 5:
            break
    if not error_lines:
        for line in reversed(lines):
            if line.strip():
                error_lines.append(line.strip())
            if len(error_lines) >= 3:
                break
    return "\n".join(reversed(error_lines))


_TIME_RE = re.compile(r"time=\s*(\d+:\d+:\d+\.\d+)")


def _get_audio_duration(audio_path: Path) -> float | None:
    """Get audio duration in seconds using ffprobe. Returns None on failure."""
    if shutil.which("ffprobe") is None:
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(audio_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return None


def _format_seconds(seconds: float) -> str:
    """Format seconds as MM:SS."""
    mins = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{mins:02d}:{secs:02d}"


def _parse_time_to_seconds(time_str: str) -> float | None:
    """Convert HH:MM:SS.ff to seconds."""
    try:
        parts = time_str.split(":")
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except (ValueError, IndexError):
        return None


def _format_progress_bar(current: float, total: float, width: int = 30) -> str:
    """Format a visual progress bar: [=====>    ] 45% (01:23 / 04:56)."""
    if total <= 0:
        return f"  {_format_seconds(current)}"
    pct = min(current / total, 1.0)
    filled = int(pct * width)
    bar = "=" * filled + ">" + " " * (width - filled - 1)
    return f"  [{bar}] {pct:5.1%} ({_format_seconds(current)} / {_format_seconds(total)})"


def _escape_drawtext(text: str) -> str:
    """Escape special characters for ffmpeg drawtext filter."""
    text = text.replace("\\", "\\\\\\\\")
    text = text.replace("'", "\\\\'")
    text = text.replace(":", "\\\\:")
    text = text.replace("%", "\\\\%")
    text = text.replace("{", "\\\\{")
    text = text.replace("}", "\\\\}")
    text = text.replace(";", "\\\\;")
    text = text.replace("\n", " ")
    text = text.replace("\r", "")
    return text


def resolve_quality(quality: str) -> QualityPreset:
    """Return the preset for a given quality label ('1080p' or '4k')."""
    key = quality.lower().strip()
    if key not in QUALITY_PRESETS:
        raise ValueError(
            f"Unknown quality '{quality}'. Available: {', '.join(QUALITY_PRESETS)}"
        )
    return QUALITY_PRESETS[key]


def validate_inputs(image_path: Path, audio_path: Path) -> None:
    """Validate that input files exist, are regular files, and have supported extensions."""
    if not image_path.is_file():
        if image_path.exists():
            raise ValueError(f"Image path is not a file: {image_path}")
        raise FileNotFoundError(f"Image file not found: {image_path}")
    if not audio_path.is_file():
        if audio_path.exists():
            raise ValueError(f"Audio path is not a file: {audio_path}")
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


def _prepare_image(
    image_path: Path,
    work_dir: Path,
    resolution: tuple[int, int],
    blur_bg: bool = True,
) -> Path:
    """Resize image to target resolution, preserving aspect ratio (contain + centered).

    When blur_bg=True (default): the empty space around the foreground is filled with
    a blurred, cover-scaled version of the same image instead of plain black bars.
    When blur_bg=False: classic black letterbox background.
    """
    target_w, target_h = resolution
    with Image.open(image_path) as raw_img:
        img = raw_img.convert("RGB")

    if img.width == 0 or img.height == 0:
        raise ValueError(f"Image has invalid dimensions {img.size}: {image_path}")

    if img.size == (target_w, target_h):
        return image_path

    img_ratio = img.width / img.height
    target_ratio = target_w / target_h

    # --- Foreground: contain (ratio preserved, centered) ---
    if img_ratio > target_ratio:
        new_w = target_w
        new_h = max(1, int(target_w / img_ratio))
    else:
        new_h = target_h
        new_w = max(1, int(target_h * img_ratio))

    fg = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    offset_x = (target_w - new_w) // 2
    offset_y = (target_h - new_h) // 2

    # --- Background ---
    if blur_bg:
        # Cover mode: scale so both dimensions >= target, then center-crop.
        # For wide images (img_ratio > target_ratio): match height, excess width cropped.
        # For tall/square images: match width, excess height cropped.
        if img_ratio > target_ratio:
            bg_h = target_h
            bg_w = max(target_w, int(target_h * img_ratio))
        else:
            bg_w = target_w
            bg_h = max(target_h, int(target_w / img_ratio))
        bg = img.resize((bg_w, bg_h), Image.Resampling.LANCZOS)
        crop_x = (bg_w - target_w) // 2
        crop_y = (bg_h - target_h) // 2
        bg = bg.crop((crop_x, crop_y, crop_x + target_w, crop_y + target_h))
        canvas = bg.filter(ImageFilter.GaussianBlur(radius=BLUR_BACKGROUND_RADIUS))
    else:
        canvas = Image.new("RGB", (target_w, target_h), (0, 0, 0))

    canvas.paste(fg, (offset_x, offset_y))
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
    blur_bg: bool = True,
    dry_run: bool = False,
    normalize: bool = False,
    title: str | None = None,
    generate_thumbnail: bool = False,
    _preset_override: str | None = None,
) -> Path:
    """
    Combine a static image and audio file into an MP4 video optimized for YouTube.

    blur_bg: when True (default), fills letterbox areas with a blurred cover-scaled
    version of the same image instead of plain black bars.

    Returns the path to the generated video.
    """
    check_ffmpeg_available()

    validate_inputs(image_path, audio_path)

    preset = resolve_quality(quality)

    res = resolution or preset.resolution
    vbr = video_bitrate or preset.video_bitrate
    fps = frame_rate or preset.frame_rate

    output_path = output_path.resolve()

    if output_path.parent.exists() and not output_path.parent.is_dir():
        raise NotADirectoryError(
            f"Output parent path already exists as a file: {output_path.parent}"
        )

    work_dir = Path(tempfile.mkdtemp(prefix="video_maker_"))

    try:
        try:
            prepared_image = _prepare_image(image_path, work_dir, res, blur_bg=blur_bg)
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError(f"Cannot read image '{image_path}': {exc}") from exc

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Map still image to video and the first *audio* stream from the file only.
        # (Many M4A/MP3/FLAC have an embedded cover as a mjpeg "video" stream; without
        # -map, ffmpeg can mis-select streams.)
        cmd = [
            "ffmpeg",
            "-y",
            "-loop", "1",
            "-i", str(prepared_image),
            "-i", str(audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", ENCODING_SETTINGS.video_codec,
            "-tune", "stillimage",
            "-preset", _preset_override or ENCODING_SETTINGS.preset,
            "-profile:v", ENCODING_SETTINGS.profile,
            "-b:v", vbr,
            "-pix_fmt", ENCODING_SETTINGS.pix_fmt,
            "-r", str(fps),
            "-c:a", ENCODING_SETTINGS.audio_codec,
            "-b:a", ENCODING_SETTINGS.audio_bitrate,
            "-ar", str(ENCODING_SETTINGS.audio_sample_rate),
            "-ac", str(ENCODING_SETTINGS.audio_channels),
        ]
        if title:
            escaped = _escape_drawtext(title)
            drawtext = (
                f"drawtext=text='{escaped}'"
                f":fontsize={TEXT_OVERLAY_FONT_SIZE}"
                f":fontcolor={TEXT_OVERLAY_FONT_COLOR}"
                f":borderw={TEXT_OVERLAY_BORDER_WIDTH}"
                f":bordercolor={TEXT_OVERLAY_BORDER_COLOR}"
                f":x=(w-text_w)/2"
                f":y=h-text_h-{TEXT_OVERLAY_Y_OFFSET}"
            )
            cmd.extend(["-vf", drawtext])
        if normalize:
            cmd.extend([
                "-af",
                f"loudnorm=I={LOUDNORM_TARGET_I}:TP={LOUDNORM_TARGET_TP}:LRA={LOUDNORM_TARGET_LRA}",
            ])
        cmd.extend([
            "-shortest",
            "-movflags", ENCODING_SETTINGS.movflags,
            str(output_path),
        ])

        logger.info("Encoding [%s %dx%d]: %s ...", quality.upper(), res[0], res[1], output_path.name)

        if dry_run:
            logger.info("[DRY RUN] Command: %s", " ".join(cmd))
            return output_path

        total_duration = _get_audio_duration(audio_path)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            stderr_lines: list[str] = []
            last_progress = 0.0
            for line in process.stderr:
                stderr_lines.append(line)
                logger.debug("ffmpeg: %s", line.rstrip())
                match = _TIME_RE.search(line)
                if match:
                    current = _parse_time_to_seconds(match.group(1))
                    if current is not None and current - last_progress >= 1.0:
                        last_progress = current
                        if total_duration:
                            progress = _format_progress_bar(current, total_duration)
                        else:
                            progress = _format_progress_bar(current, 0)
                        sys.stderr.write(f"\r{progress}")
                        sys.stderr.flush()

            returncode = process.wait()
            sys.stderr.write("\n")
        except BaseException:
            process.kill()
            process.wait()
            raise

        if returncode != 0:
            full_stderr = "".join(stderr_lines)
            logger.debug("ffmpeg stderr:\n%s", full_stderr)
            clean_error = _parse_ffmpeg_error(full_stderr)
            raise RuntimeError(
                f"ffmpeg failed (exit code {returncode}):\n{clean_error}"
            )

        if output_path.exists():
            size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.info("Done! Output: %s (%.1f MB)", output_path, size_mb)
        else:
            logger.info("Done! Output: %s", output_path)

        if generate_thumbnail:
            thumb_path = output_path.parent / f"{output_path.stem}{THUMBNAIL_SUFFIX}.jpg"
            with Image.open(prepared_image) as thumb_img:
                thumb = thumb_img.convert("RGB")
                thumb = thumb.resize(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                thumb.save(thumb_path, THUMBNAIL_FORMAT, quality=90)
            logger.info("Thumbnail: %s", thumb_path)

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    return output_path


@dataclasses.dataclass
class TrackItem:
    """One batch job: one audio, one static image, one output .mp4 filename (basename)."""
    audio_path: Path
    image_path: Path
    output_filename: str  # e.g. "01-intro.mp4" (not a full path)


@dataclasses.dataclass
class BatchResult:
    """Structured result from batch encoding."""
    successes: list[Path]
    failures: list[tuple[Path, str]]
    track_results: list[TrackResult] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class TrackResult:
    """Per-track result for batch summary."""
    name: str
    status: str  # "ok", "failed", "skipped"
    elapsed: float = 0.0
    size_bytes: int = 0

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)


def _is_under_dir(parent: Path, child: Path) -> bool:
    try:
        child = child.resolve()
        parent = parent.resolve()
        return parent in child.parents or child == parent
    except OSError:
        return False


def _file_in_input_dir(input_dir: Path, relative: str) -> Path | None:
    """Return a resolved file path if it exists under input_dir (no path escape)."""
    if not relative or not relative.strip():
        return None
    candidate = (input_dir / relative.strip().replace("\\", "/")).resolve()
    if not _is_under_dir(input_dir, candidate) or not candidate.is_file():
        return None
    return candidate


def _build_image_index(input_dir: Path) -> dict[str, Path]:
    """Build a {stem_lower: Path} index of all images in input_dir (flat, no subdirs)."""
    index: dict[str, Path] = {}
    for f in input_dir.iterdir():
        if f.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            index.setdefault(f.stem.lower(), f)
    return index


def _load_tracks_manifest(input_dir: Path) -> dict | None:
    path = input_dir / TRACKS_MANIFEST_FILENAME
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "%s is not valid JSON (%s); using folder scan and name-matching mode.",
            TRACKS_MANIFEST_FILENAME, exc,
        )
        return None
    if not isinstance(data, dict):
        logger.warning(
            "%s root must be a JSON object; ignoring manifest.",
            TRACKS_MANIFEST_FILENAME,
        )
        return None
    if "tracks" in data and not isinstance(data.get("tracks"), list):
        logger.warning(
            "%s 'tracks' must be a list; ignoring manifest.",
            TRACKS_MANIFEST_FILENAME,
        )
        return None
    return data


def _normalize_output_name(name: str) -> str:
    name = name.strip()
    if not name:
        return name
    # Reject path traversal: only accept a simple filename (no / or ..)
    if "/" in name or "\\" in name or ".." in name:
        return ""
    if not name.lower().endswith(".mp4"):
        name = f"{name}.mp4"
    return name


def _resolve_image_for_track(
    input_dir: Path,
    audio_stem: str,
    manifest_entry: dict | None,
    default_cover: str | None,
    global_cover: Path | None,
    image_index: dict[str, Path],
) -> Path | None:
    """Resolve which image to use: manifest 'image' > default_cover > name match > global cover."""
    if manifest_entry and isinstance(manifest_entry.get("image"), str) and manifest_entry["image"].strip():
        p = _file_in_input_dir(input_dir, manifest_entry["image"].strip().replace("\\", "/"))
        if p and p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            return p
    if default_cover:
        p = _file_in_input_dir(input_dir, default_cover.strip().replace("\\", "/"))
        if p and p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            return p
    matched = image_index.get(audio_stem.lower())
    if matched:
        return matched
    return global_cover


_NO_IMAGE_MSG = (
    "No image: add a cover ({cover!r}.*), a same-stem image as the audio, "
    "or per-track 'image' in {mf}."
)


def _resolve_track_pairs(
    input_dir: Path,
    image_name: str,
) -> tuple[list[TrackItem], list[tuple[Path, str]], str]:
    """
    Build (audio, image, output) jobs. Returns
    (track_items, pre_failures, mode) where mode is 'manifest' or 'scan'.
    pre_failures are (audio_path, reason) for tracks that could not get an image.
    """
    input_dir = input_dir.resolve()
    if not input_dir.is_dir():
        return [], [], "scan"

    no_img = _NO_IMAGE_MSG.format(cover=image_name, mf=TRACKS_MANIFEST_FILENAME)
    image_index = _build_image_index(input_dir)
    global_cover = image_index.get(image_name.lower())
    manifest = _load_tracks_manifest(input_dir)
    pre_failures: list[tuple[Path, str]] = []

    if manifest is not None and isinstance(manifest.get("tracks"), list):
        if len(manifest["tracks"]) == 0:
            return [], [], "manifest"
        default_rel: str | None = None
        if isinstance(manifest.get("default_cover"), str) and manifest["default_cover"].strip():
            default_rel = manifest["default_cover"].strip().replace("\\", "/")
        items: list[TrackItem] = []
        for entry in manifest.get("tracks", []):
            if not isinstance(entry, dict):
                continue
            if not entry.get("audio") or not isinstance(entry["audio"], str):
                continue
            rel_audio = entry["audio"].strip()
            ap = _file_in_input_dir(input_dir, rel_audio)
            if ap is None or ap.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
                continue
            if isinstance(entry.get("output"), str) and entry["output"].strip():
                out_name = _normalize_output_name(entry["output"].strip())
            else:
                out_name = f"{ap.stem}.mp4"
            img = _resolve_image_for_track(
                input_dir,
                ap.stem,
                entry,
                default_rel,
                global_cover,
                image_index,
            )
            if not img:
                pre_failures.append((ap, no_img))
                continue
            items.append(TrackItem(audio_path=ap, image_path=img, output_filename=out_name))
        return items, pre_failures, "manifest"

    # Folder scan: every audio file, no valid manifest
    audio_files = sorted(
        f
        for f in input_dir.iterdir()
        if f.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
    )
    if not audio_files:
        return [], [], "scan"
    items = []
    for af in audio_files:
        img = _resolve_image_for_track(
            input_dir,
            af.stem,
            None,
            None,
            global_cover,
            image_index,
        )
        if not img:
            pre_failures.append((af, no_img))
            continue
        items.append(
            TrackItem(
                audio_path=af,
                image_path=img,
                output_filename=f"{af.stem}.mp4",
            )
        )
    return items, pre_failures, "scan"


def _print_batch_summary(track_results: list[TrackResult]) -> None:
    """Print a formatted summary table for batch results."""
    name_w = max(len(tr.name) for tr in track_results)
    name_w = max(name_w, 4)  # minimum header width
    header = f"  {'File':<{name_w}}  {'Status':<8}  {'Size':>10}  {'Time':>8}"
    logger.info(header)
    logger.info("  " + "-" * (len(header) - 2))
    for tr in track_results:
        size_str = f"{tr.size_mb:.1f} MB" if tr.size_bytes else "-"
        elapsed_str = _format_seconds(tr.elapsed) if tr.elapsed > 0 else "-"
        logger.info(
            f"  {tr.name:<{name_w}}  {tr.status:<8}  {size_str:>10}  {elapsed_str:>8}"
        )


def _estimate_batch_size(track_items: list[TrackItem], preset: QualityPreset) -> int:
    """Rough estimate of total output size in bytes.

    Uses a heuristic: video_bitrate * assumed 4-minute average per track.
    """
    # Parse bitrate string (e.g. "8M" -> 8_000_000)
    vbr_str = preset.video_bitrate.upper()
    multiplier = {"K": 1000, "M": 1_000_000, "G": 1_000_000_000}
    vbr_bps = int(float("".join(c for c in vbr_str if c.isdigit() or c == ".")) * multiplier.get(vbr_str[-1], 1))
    estimated_per_track = vbr_bps * 4 * 60  # assume ~4 min average
    return estimated_per_track * len(track_items)


def _encode_single_track(
    item: TrackItem,
    output_dir: Path,
    quality: str,
    blur_bg: bool,
    dry_run: bool,
    skip_existing: bool,
    normalize: bool = False,
    title: str | None = None,
    generate_thumbnail: bool = False,
    retry: bool = True,
) -> tuple[Path | None, tuple[Path, str] | None, TrackResult]:
    """Encode a single track. Returns (success_path, failure_or_none, track_result).

    When retry=True and ffmpeg fails with RuntimeError, retries once with the
    ultrafast preset before giving up.
    """
    out_path = output_dir / item.output_filename
    if skip_existing and out_path.exists() and out_path.is_file():
        if (out_path.stat().st_size > 0
                and out_path.stat().st_mtime >= item.audio_path.stat().st_mtime):
            logger.info("  SKIP (already encoded): %s", item.output_filename)
            size = out_path.stat().st_size
            return out_path, None, TrackResult(item.output_filename, "skipped", 0.0, size)
    if dry_run:
        logger.info("[DRY RUN] Would encode: %s", item.output_filename)
        return out_path, None, TrackResult(item.output_filename, "ok")
    t0 = time.monotonic()
    try:
        result = encode_video(
            image_path=item.image_path,
            audio_path=item.audio_path,
            output_path=out_path,
            quality=quality,
            blur_bg=blur_bg,
            normalize=normalize,
            title=title,
            generate_thumbnail=generate_thumbnail,
        )
        elapsed = time.monotonic() - t0
        size = result.stat().st_size if result.exists() else 0
        return result, None, TrackResult(item.output_filename, "ok", elapsed, size)
    except RuntimeError as exc:
        if retry:
            logger.warning(
                "  RETRY: %s failed, retrying with ultrafast preset...",
                item.output_filename,
            )
            try:
                result = encode_video(
                    image_path=item.image_path,
                    audio_path=item.audio_path,
                    output_path=out_path,
                    quality=quality,
                    blur_bg=blur_bg,
                    normalize=normalize,
                    title=title,
                    generate_thumbnail=generate_thumbnail,
                    _preset_override="ultrafast",
                )
                elapsed = time.monotonic() - t0
                size = result.stat().st_size if result.exists() else 0
                return result, None, TrackResult(item.output_filename, "ok", elapsed, size)
            except (RuntimeError, ValueError) as retry_exc:
                elapsed = time.monotonic() - t0
                logger.warning("  SKIP (retry also failed): %s", retry_exc)
                return None, (item.audio_path, str(retry_exc)), TrackResult(item.output_filename, "failed", elapsed)
        elapsed = time.monotonic() - t0
        logger.warning("  SKIP: %s", exc)
        return None, (item.audio_path, str(exc)), TrackResult(item.output_filename, "failed", elapsed)
    except ValueError as exc:
        elapsed = time.monotonic() - t0
        logger.warning("  SKIP: %s", exc)
        return None, (item.audio_path, str(exc)), TrackResult(item.output_filename, "failed", elapsed)


def batch_encode(
    input_dir: Path,
    output_dir: Path,
    quality: str = "1080p",
    image_name: str = "cover",
    blur_bg: bool = True,
    dry_run: bool = False,
    skip_existing: bool = False,
    max_workers: int = 1,
    normalize: bool = False,
    title: str | None = None,
    generate_thumbnail: bool = False,
    retry: bool = True,
) -> BatchResult:
    """Batch-encode from input_dir. Pairing of image + audio:

    1) If `tracks.json` is valid, its ``tracks`` list is used (in order) with
       optional per-track ``image``, optional ``default_cover`` at the root, and
       optional ``output`` (defaults to <audio_stem>.mp4).
    2) If no manifest (or invalid JSON, printed as warning), every audio file
       in the folder is processed; image = same-stem file if present, else
       `image_name` (default ``cover``).
    3) For each job, the first available among: per-track image, default_cover,
       name-matched image, global cover.

    A global `image_name` cover (e.g. cover.jpg) is not required if every
    resolved track has a specific image.

    Returns a BatchResult with successes and failures.
    """
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {input_dir}")
    if output_dir.exists() and not output_dir.is_dir():
        raise NotADirectoryError(f"Output path already exists as a file: {output_dir}")

    idir = input_dir.resolve()
    track_items, pre_failures, mode = _resolve_track_pairs(idir, image_name)
    encode_failures: list[tuple[Path, str]] = list(pre_failures)

    if track_items:
        out_names = [i.output_filename for i in track_items]
        if len(out_names) != len(set(out_names)):
            dups = sorted(k for k, v in Counter(out_names).items() if v > 1)
            raise ValueError(
                "Duplicate output name(s) in this batch: "
                f"{dups!r}. Set unique 'output' values in "
                f"{TRACKS_MANIFEST_FILENAME} or rename input files."
            )

    if not track_items:
        if mode == "manifest" and not encode_failures:
            if (idir / TRACKS_MANIFEST_FILENAME).is_file():
                try:
                    with (idir / TRACKS_MANIFEST_FILENAME).open(encoding="utf-8") as f:
                        raw = json.load(f)
                    if (
                        isinstance(raw, dict)
                        and isinstance(raw.get("tracks"), list)
                        and len(raw["tracks"]) == 0
                    ):
                        raise FileNotFoundError(
                            f"No entries in {TRACKS_MANIFEST_FILENAME} 'tracks' in {idir}."
                        )
                except (OSError, json.JSONDecodeError):
                    pass
            raise FileNotFoundError(
                f"No valid audio entries in {TRACKS_MANIFEST_FILENAME} in {idir}."
            )
        if encode_failures:
            return BatchResult(successes=[], failures=encode_failures)
        raise FileNotFoundError(f"No audio files found in {idir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Disk space check
    if not dry_run:
        preset = resolve_quality(quality)
        estimated = _estimate_batch_size(track_items, preset)
        disk_free = shutil.disk_usage(output_dir).free
        if disk_free < estimated:
            free_gb = disk_free / (1024 ** 3)
            need_gb = estimated / (1024 ** 3)
            raise OSError(
                f"Insufficient disk space: {free_gb:.1f} GB free, "
                f"estimated {need_gb:.1f} GB needed for {len(track_items)} video(s)."
            )

    logger.info(
        "Batch mode: %d job(s) (%s)",
        len(track_items),
        "manifest" if mode == "manifest" else "folder scan",
    )
    logger.info("Quality: %s | Output: %s", quality, output_dir)
    if pre_failures:
        logger.info("-" * 50)
    for p, reason in pre_failures:
        logger.warning("  SKIP: %s — %s", p.name, reason)
    if pre_failures:
        logger.info("-" * 50)

    for i, item in enumerate(track_items, 1):
        logger.info(
            "\n[%d/%d] %s + %s -> %s",
            i, len(track_items),
            item.audio_path.name,
            item.image_path.name,
            item.output_filename,
        )

    successes: list[Path] = []
    skipped: list[Path] = []
    track_results: list[TrackResult] = []

    if max_workers > 1 and not dry_run:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        logger.info("Parallel encoding with %d worker(s)", max_workers)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _encode_single_track, item, output_dir, quality, blur_bg, dry_run, skip_existing, normalize, title, generate_thumbnail, retry
                ): item
                for item in track_items
            }
            for future in as_completed(futures):
                success_path, failure, tr = future.result()
                track_results.append(tr)
                if success_path:
                    successes.append(success_path)
                    if tr.status == "skipped":
                        skipped.append(success_path)
                if failure:
                    encode_failures.append(failure)
    else:
        for item in track_items:
            success_path, failure, tr = _encode_single_track(
                item, output_dir, quality, blur_bg, dry_run, skip_existing, normalize, title, generate_thumbnail, retry,
            )
            track_results.append(tr)
            if success_path:
                successes.append(success_path)
                if tr.status == "skipped":
                    skipped.append(output_dir / item.output_filename)
            if failure:
                encode_failures.append(failure)

    logger.info("-" * 50)
    total = len(track_items) + len(pre_failures)
    logger.info("Batch complete: %d/%d video(s) generated.", len(successes), total)
    if skipped:
        logger.info("Skipped (already encoded): %d file(s)", len(skipped))
    if encode_failures:
        logger.warning("Failed: %d file(s)", len(encode_failures))
        for failed_path, err in encode_failures:
            logger.warning("  - %s: %s", failed_path.name, err)

    # Summary table
    if track_results:
        _print_batch_summary(track_results)

    return BatchResult(successes=successes, failures=encode_failures, track_results=track_results)
