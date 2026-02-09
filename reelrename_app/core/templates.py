from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from reelrename_app.core.classifier import MediaType
from reelrename_app.core.parser import ParsedMedia
from reelrename_app.core.naming import proposed_name


_WINDOWS_FORBIDDEN = r'<>:"/\\|?*'
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f]")


def sanitize_component(name: str) -> str:
    """
    Make a filename/path component safe across Windows/Linux.
    """
    name = _CONTROL_CHARS_RE.sub("", name)
    name = name.strip().strip(".")  # avoid trailing dots on Windows
    name = "".join("_" if c in _WINDOWS_FORBIDDEN else c for c in name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name or "Unknown"


def season_folder(season: Optional[int]) -> str:
    s = season if season is not None else 1
    return f"Season {s:02d}"


def build_destination(
    src: Path,
    parsed: ParsedMedia,
    media_type: MediaType,
    library_root: Optional[Path],
    move_enabled: bool,
) -> Path:
    """
    Returns the FULL destination path for the file.
    - If move_enabled=False: rename in place.
    - If move_enabled=True: move under library_root with folder templates.
    """
    ext = src.suffix.lower()

    # Always generate a conservative base filename
    new_filename = proposed_name(parsed, media_type, ext)
    new_filename = sanitize_component(new_filename)

    if not move_enabled or library_root is None:
        return (src.parent / new_filename).resolve()

    root = library_root.resolve()

    # Folder templates
    if media_type == MediaType.MOVIE:
        title = sanitize_component(parsed.title or "Unknown Title")
        folder = title
        if parsed.year:
            folder = sanitize_component(f"{title} ({parsed.year})")
        dest_dir = root / "Movies" / folder
        return (dest_dir / new_filename).resolve()

    if media_type == MediaType.TV:
        show = sanitize_component(parsed.title or "Unknown Show")
        sdir = season_folder(parsed.season)
        dest_dir = root / "TV Shows" / show / sdir
        return (dest_dir / new_filename).resolve()


    if media_type == MediaType.ANIME:
        title = sanitize_component(parsed.title or "Unknown Anime")
        sdir = season_folder(parsed.season)
        dest_dir = root / "Anime" / title / sdir
        return (dest_dir / new_filename).resolve()

    if media_type == MediaType.ANIME_MOVIE:
        title = sanitize_component(parsed.title or "Unknown Anime Movie")
        folder = title
        if parsed.year:
            folder = sanitize_component(f"{title} ({parsed.year})")
        dest_dir = root / "Anime Movies" / folder
        return (dest_dir / new_filename).resolve()

    # Unknown
    dest_dir = root / "Unsorted"
    return (dest_dir / new_filename).resolve()
