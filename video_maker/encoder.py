"""Core video encoding logic using ffmpeg."""

from __future__ import annotations

import dataclasses
import json
from collections import Counter
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from video_maker.settings import (
    ENCODING_SETTINGS,
    QUALITY_PRESETS,
    SUPPORTED_AUDIO_EXTENSIONS,
    SUPPORTED_IMAGE_EXTENSIONS,
    TRACKS_MANIFEST_FILENAME,
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


def _prepare_image(image_path: Path, work_dir: Path, resolution: tuple[int, int]) -> Path:
    """Resize image to target resolution with letterboxing to preserve aspect ratio."""
    target_w, target_h = resolution
    with Image.open(image_path) as raw_img:
        img = raw_img.convert("RGB")

    if img.width == 0 or img.height == 0:
        raise ValueError(f"Image has invalid dimensions {img.size}: {image_path}")

    if img.size == (target_w, target_h):
        return image_path

    img_ratio = img.width / img.height
    target_ratio = target_w / target_h
    if img_ratio > target_ratio:
        new_w = target_w
        new_h = max(1, int(target_w / img_ratio))
    else:
        new_h = target_h
        new_w = max(1, int(target_h * img_ratio))

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
        try:
            prepared_image = _prepare_image(image_path, work_dir, res)
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
        print(
            f"Warning: {TRACKS_MANIFEST_FILENAME} is not valid JSON ({exc}); "
            f"using folder scan and name-matching mode.",
            file=sys.stderr,
        )
        return None
    if not isinstance(data, dict):
        return None
    if "tracks" in data and not isinstance(data.get("tracks"), list):
        print(
            f"Warning: {TRACKS_MANIFEST_FILENAME} 'tracks' must be a list; "
            f"ignoring manifest.",
            file=sys.stderr,
        )
        return None
    return data


def _normalize_output_name(name: str) -> str:
    name = name.strip()
    if not name:
        return name
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


def batch_encode(
    input_dir: Path,
    output_dir: Path,
    quality: str = "1080p",
    image_name: str = "cover",
) -> BatchResult:
    """
    Batch-encode from input_dir. Pairing of image + audio:

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
        if mode == "manifest" and encode_failures:
            return BatchResult(successes=[], failures=encode_failures)
        any_audio = any(
            f.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
            for f in idir.iterdir()
        )
        if not any_audio and not encode_failures:
            raise FileNotFoundError(f"No audio files found in {idir}")
        if encode_failures and not track_items:
            return BatchResult(successes=[], failures=encode_failures)
        if not any_audio:
            raise FileNotFoundError(f"No audio files found in {idir}")
        raise FileNotFoundError(
            f"No image could be assigned to any encodable track in {idir}. "
            f"Add a {image_name!r} image, per-audio art with the same name as the audio, "
            f"or a valid {TRACKS_MANIFEST_FILENAME}."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"Batch mode: {len(track_items)} job(s) "
        f"({'manifest' if mode == 'manifest' else 'folder scan'})"
    )
    print(f"Quality: {quality} | Output: {output_dir}")
    if pre_failures:
        print("-" * 50)
    for p, reason in pre_failures:
        print(f"  SKIP: {p.name} — {reason}", file=sys.stderr)
    if pre_failures:
        print("-" * 50)

    successes: list[Path] = []
    for i, item in enumerate(track_items, 1):
        out_path = output_dir / item.output_filename
        print(
            f"\n[{i}/{len(track_items)}] {item.audio_path.name} + "
            f"{item.image_path.name} -> {item.output_filename}"
        )
        try:
            result = encode_video(
                image_path=item.image_path,
                audio_path=item.audio_path,
                output_path=out_path,
                quality=quality,
            )
            successes.append(result)
        except (RuntimeError, ValueError) as exc:
            print(f"  SKIP: {exc}", file=sys.stderr)
            encode_failures.append((item.audio_path, str(exc)))

    print("-" * 50)
    total = len(track_items) + len(pre_failures)
    print(f"Batch complete: {len(successes)}/{total} video(s) generated.")
    if encode_failures:
        print(f"Failed: {len(encode_failures)} file(s)", file=sys.stderr)
        for failed_path, err in encode_failures:
            print(f"  - {failed_path.name}: {err}", file=sys.stderr)

    return BatchResult(successes=successes, failures=encode_failures)
