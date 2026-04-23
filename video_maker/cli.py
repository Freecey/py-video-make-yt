"""CLI interface for video-maker-auto."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from video_maker.encoder import encode_video, batch_encode
from video_maker.settings import QUALITY_PRESETS


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="video-maker",
        description="Combine a static image + audio into a YouTube-optimized MP4 video.",
    )

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

    if args.command == "batch":
        output_dir = args.output_dir or args.input_dir / "output"
        try:
            result = batch_encode(
                input_dir=args.input_dir.resolve(),
                output_dir=output_dir.resolve(),
                quality=args.quality,
                image_name=args.cover_name,
            )
        except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0 if not result.failures else 1

    if args.command == "single":
        output_path = args.output or Path.cwd() / f"{args.audio.stem}.mp4"
        resolution = _parse_resolution(args.resolution)
        if args.resolution and resolution is None:
            print(
                "Error: --resolution must be in WxH format with positive values "
                "(e.g. 1920x1080).",
                file=sys.stderr,
            )
            return 1

        try:
            encode_video(
                image_path=args.image.resolve(),
                audio_path=args.audio.resolve(),
                output_path=output_path.resolve(),
                quality=args.quality,
                resolution=resolution,
                video_bitrate=args.bitrate,
                frame_rate=args.fps,
            )
        except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except RuntimeError as exc:
            print(f"Encoding error: {exc}", file=sys.stderr)
            return 1
        return 0

    # No subcommand: show help and exit
    parse_args(["--help"])


if __name__ == "__main__":
    sys.exit(main())
