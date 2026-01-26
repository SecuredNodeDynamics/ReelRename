from __future__ import annotations

import re
from dataclasses import replace
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


def _infer_series_title_from_path(src: Path) -> Optional[str]:
    """
    Infer a series title from folder structure.

    Examples:
      .../Dragon Raja/Season 1/S01E01.mkv      -> Dragon Raja
      .../Dragon Raja/Season 01/Episode 1.mkv  -> Dragon Raja
      .../Dragon Raja/S01E01.mkv               -> Dragon Raja

    Strategy:
      - If parent folder looks like a season folder, use its parent as show folder.
      - Otherwise, use the immediate parent folder.
    """
    try:
        parent = src.parent
        if not parent or parent == parent.parent:
            return None

        p = parent.name.strip()
        if not p:
            return None

        # Detect "Season 1", "Season 01", "S1", "S01"
        season_like = bool(re.match(r"^(season\s*\d+|s\d{1,2})$", p, flags=re.IGNORECASE))

        show_folder = parent.parent if season_like else parent
        name = show_folder.name.strip()
        return name or None
    except Exception:
        return None


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

    # If series episode (TV or Anime with episode) and title is missing,
    # infer title from the folder name and inject it into parsing.
    if (media_type == MediaType.TV) or (media_type == MediaType.ANIME and parsed.episode is not None):
        if not (parsed.title and parsed.title.strip()):
            inferred = _infer_series_title_from_path(src)
            if inferred:
                parsed = replace(parsed, title=inferred)

    # Always generate a conservative base filename
    new_filename = proposed_name(parsed, media_type, ext)
    new_filename = sanitize_component(new_filename)

    if not move_enabled or library_root is None:
        return (src.parent / new_filename).resolve()

    root = library_root.resolve()

    # Folder templates
    if media_type == MediaType.MOVIE:
        # For movies, keep a fallback, but NOT for series episodes.
        title = sanitize_component(parsed.title or "Unknown")
        folder = title
        if parsed.year:
            folder = sanitize_component(f"{title} ({parsed.year})")
        dest_dir = root / "Movies" / folder
        return (dest_dir / new_filename).resolve()

    if media_type == MediaType.TV:
        # Prefer parsed title; if still missing, use a neutral fallback folder.
        show_name = parsed.title.strip() if parsed.title else ""
        show = sanitize_component(show_name or "TV")
        sdir = season_folder(parsed.season)
        dest_dir = root / "TV Shows" / show / sdir
        return (dest_dir / new_filename).resolve()

    if media_type == MediaType.ANIME:
        # If it has an episode number, treat as series; otherwise treat as anime movie
        title_text = (parsed.title or "").strip()

        if parsed.episode is not None:
            # Series: title should already be inferred above if missing.
            show = sanitize_component(title_text or "Anime")
            sdir = season_folder(parsed.season)
            dest_dir = root / "Anime" / show / sdir
            return (dest_dir / new_filename).resolve()

        # Anime movie / special
        title = sanitize_component(title_text or "Unknown")
        folder = title
        if parsed.year:
            folder = sanitize_component(f"{title} ({parsed.year})")
        dest_dir = root / "Anime Movies" / folder
        return (dest_dir / new_filename).resolve()

    # Unknown
    dest_dir = root / "Unsorted"
    return (dest_dir / new_filename).resolve()
