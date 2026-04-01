from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Set


MEDIA_EXTS: Set[str] = {
    ".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv", ".flv", ".webm"
}


@dataclass(frozen=True)
class MediaItem:
    path: Path

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def ext(self) -> str:
        return self.path.suffix.lower()

    @property
    def parent(self) -> str:
        return str(self.path.parent)


def is_media_file(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in MEDIA_EXTS


def scan_paths(paths: Iterable[str]) -> List[MediaItem]:
    """
    Accepts file/folder paths.
    - Files: include if media
    - Folders: recursively add media files
    De-dupes by resolved absolute path.
    """
    found: List[MediaItem] = []
    seen: Set[Path] = set()

    for raw in paths:
        p = Path(raw).expanduser()
        if not p.exists():
            continue

        if p.is_file():
            if is_media_file(p):
                rp = p.resolve()
                if rp not in seen:
                    seen.add(rp)
                    found.append(MediaItem(rp))
            continue

        if p.is_dir():
            for f in p.rglob("*"):
                if is_media_file(f):
                    rp = f.resolve()
                    if rp not in seen:
                        seen.add(rp)
                        found.append(MediaItem(rp))

    found.sort(key=_sort_key)
    return found


# Matches a stem that ends with  -<digits>  e.g. "ShowName-02" or "ShowName - 02"
_TRAILING_NUM_RE = re.compile(r'^(.*?)-\s*(\d+)$')


def _sort_key(item: MediaItem) -> tuple:
    """
    Sort by parent folder, then by base name and trailing dash-number.
    A file with no trailing -XX suffix is assigned num=0 so it always
    sorts before -02, -03, etc.
    Example order: ShowName.mkv → ShowName-02.mkv → ShowName-03.mkv
    """
    stem = item.path.stem.lower()
    m = _TRAILING_NUM_RE.match(stem)
    if m:
        base = m.group(1).rstrip()
        num = int(m.group(2))
    else:
        base = stem
        num = 0
    return (item.parent.lower(), base, num, item.name.lower())
