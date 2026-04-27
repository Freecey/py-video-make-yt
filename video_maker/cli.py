"""CLI interface for video-maker-auto."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from video_maker.config import UserConfig, load_config
from video_maker.encoder import encode_video, batch_encode
from video_maker.settings import QUALITY_PRESETS

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stderr,
        force=True,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="video-maker",
        description="Combine a static image + audio into a YouTube-optimized MP4 video.",
    )
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show debug output (full ffmpeg stderr, etc.).")
    parser.add_argument("--config", type=Path, default=None,
                        help="Path to config file. Defaults to ~/.video-maker.toml")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be encoded without running ffmpeg.")

    sub = parser.add_subparsers(dest="command")

    # --- single mode ---
    single = sub.add_parser("single", help="Encode one video from an image + audio file.")
    single.add_argument("-i", "--image", type=Path, required=True,
                        help="Path to the image file (jpg, png, bmp, webp, tiff).")
    single.add_argument("-a", "--audio", type=Path, required=True,
                        help="Path to the audio file (mp3, wav, aac, m4a, ogg, opus, flac, wma).")
    single.add_argument("-o", "--output", type=Path, default=None,
                        help="Output video path. Defaults to <audio_name>.mp4 in current directory.")
    single.add_argument("-q", "--quality", type=str, default="1080p",
                        choices=list(QUALITY_PRESETS.keys()),
                        help="Quality preset (default: 1080p).")
    single.add_argument("--resolution", type=str, default=None,
                        help="Override resolution as WxH (e.g. 1920x1080). Overrides --quality resolution.")
    single.add_argument("--bitrate", type=str, default=None,
                        help=f"Override video bitrate (default from preset).")
    single.add_argument("--fps", type=int, default=None,
                        help=f"Override frame rate (default from preset).")
    single.add_argument("--no-blur-bg", dest="blur_bg", action="store_false",
                        help="Disable blurred background; use plain black letterbox instead.")
    single.add_argument("--normalize", action="store_true",
                        help="Normalize audio loudness to YouTube standard (EBU R128).")
    single.add_argument("--title", type=str, default=None,
                        help="Overlay text on the video (centered, near bottom).")
    single.add_argument("--thumbnail", action="store_true",
                        help="Generate a 1280x720 thumbnail JPEG next to the output video.")

    # --- batch mode ---
    batch = sub.add_parser(
        "batch",
        help=(
            "Encode many audios: optional tracks.json (per-track image + output), "
            "or folder scan (same-stem image per audio, else cover.*)."
        ),
    )
    batch.add_argument(
        "input_dir",
        type=Path,
        help=(
            "Folder with audio files. If tracks.json exists and is valid JSON, use it; "
            "otherwise process all audios in order. Cover (see --cover-name) is the fallback image."
        ),
    )
    batch.add_argument("-o", "--output-dir", type=Path, default=None,
                       help="Output folder for videos. Defaults to <input_dir>/output.")
    batch.add_argument("-q", "--quality", type=str, default="1080p",
                       choices=list(QUALITY_PRESETS.keys()),
                       help="Quality preset (default: 1080p).")
    batch.add_argument("--cover-name", type=str, default="cover",
                       help="Name of the cover image file (without extension). Default: cover.")
    batch.add_argument("--no-blur-bg", dest="blur_bg", action="store_false",
                       help="Disable blurred background; use plain black letterbox instead.")
    batch.add_argument("--skip-existing", action="store_true",
                       help="Skip encoding if output video already exists and is newer than the audio source.")
    batch.add_argument("-j", "--jobs", type=int, default=1,
                       help="Number of parallel encoding jobs (default: 1, sequential).")
    batch.add_argument("--normalize", action="store_true",
                       help="Normalize audio loudness to YouTube standard (EBU R128).")
    batch.add_argument("--title", type=str, default=None,
                       help="Overlay text on all videos (centered, near bottom).")
    batch.add_argument("--thumbnail", action="store_true",
                       help="Generate a 1280x720 thumbnail JPEG next to each output video.")

    return parser.parse_args(argv)


def _parse_resolution(resolution_str: str | None) -> tuple[int, int] | None:
    if not resolution_str:
        return None
    parts = resolution_str.lower().split("x")
    if len(parts) != 2:
        return None
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if w <= 0 or h <= 0:
        return None
    return (w, h)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)

    config = load_config(args.config)

    # No subcommand: show help and exit
    if not args.command:
        parse_args(["--help"])

    # Apply config defaults (CLI flags always override config)
    # blur_bg: argparse default is True (store_false for --no-blur-bg), so we
    # can't distinguish "not set" from "explicitly True". Only override from
    # config when the user used --no-blur-bg (False) or config has False.
    blur_bg = args.blur_bg
    if config.blur_bg is not None and blur_bg and not config.blur_bg:
        blur_bg = False
    normalize = args.normalize or (config.normalize or False)
    title = args.title or config.title
    quality = args.quality if args.quality != "1080p" else (config.quality or args.quality)
    if quality not in QUALITY_PRESETS:
        quality = "1080p"

    if args.command == "batch":
        output_dir = args.output_dir or (
            Path(config.output_dir) if config.output_dir else None
        ) or args.input_dir / "output"
        try:
            result = batch_encode(
                input_dir=args.input_dir.resolve(),
                output_dir=output_dir.resolve(),
                quality=quality,
                image_name=args.cover_name,
                blur_bg=blur_bg,
                dry_run=args.dry_run,
                skip_existing=args.skip_existing,
                max_workers=args.jobs,
                normalize=normalize,
                title=title,
                generate_thumbnail=args.thumbnail,
            )
        except (FileNotFoundError, NotADirectoryError, ValueError, OSError) as exc:
            logger.error("Error: %s", exc)
            return 1
        return 0 if not result.failures else 1

    if args.command == "single":
        output_path = args.output or Path.cwd() / f"{args.audio.stem}.mp4"
        resolution = _parse_resolution(args.resolution)
        if args.resolution and resolution is None:
            logger.error(
                "Error: --resolution must be in WxH format with positive values "
                "(e.g. 1920x1080).",
            )
            return 1

        try:
            encode_video(
                image_path=args.image.resolve(),
                audio_path=args.audio.resolve(),
                output_path=output_path.resolve(),
                quality=quality,
                resolution=resolution,
                video_bitrate=args.bitrate,
                frame_rate=args.fps,
                blur_bg=blur_bg,
                dry_run=args.dry_run,
                normalize=normalize,
                title=title,
                generate_thumbnail=args.thumbnail,
            )
        except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
            logger.error("Error: %s", exc)
            return 1
        except RuntimeError as exc:
            logger.error("Encoding error: %s", exc)
            return 1
        return 0

    # No subcommand: show help and exit
    parse_args(["--help"])


if __name__ == "__main__":
    sys.exit(main())
