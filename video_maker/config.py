"""Configuration file loading for video-maker-auto."""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

CONFIG_FILENAME = ".video-maker.toml"


@dataclasses.dataclass
class UserConfig:
    quality: str | None = None
    output_dir: str | None = None
    blur_bg: bool | None = None
    normalize: bool | None = None
    title: str | None = None


def load_config(path: Path | None = None) -> UserConfig:
    """Load user config from TOML file. Returns UserConfig with None for unset fields."""
    if path is None:
        path = Path.home() / CONFIG_FILENAME
    if not path.is_file():
        return UserConfig()
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        logger.warning("Cannot read config %s: %s", path, exc)
        return UserConfig()
    section = data.get("video-maker", data)
    if not isinstance(section, dict):
        return UserConfig()
    return UserConfig(
        quality=section.get("quality") if isinstance(section.get("quality"), str) else None,
        output_dir=section.get("output_dir") if isinstance(section.get("output_dir"), str) else None,
        blur_bg=section.get("blur_bg") if isinstance(section.get("blur_bg"), bool) else None,
        normalize=section.get("normalize") if isinstance(section.get("normalize"), bool) else None,
        title=section.get("title") if isinstance(section.get("title"), str) else None,
    )
