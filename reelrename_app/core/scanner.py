from __future__ import annotations

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

    found.sort(key=lambda x: (x.parent.lower(), x.name.lower()))
    return found
