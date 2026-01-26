from __future__ import annotations

from enum import Enum
from reelrename_app.core.parser import ParsedMedia


class MediaType(str, Enum):
    MOVIE = "Movie"
    TV = "TV"
    ANIME = "Anime"
    UNKNOWN = "Unknown"


def classify(parsed: ParsedMedia) -> MediaType:
    # Strong signals
    if parsed.is_anime:
        return MediaType.ANIME

    if parsed.season is not None and parsed.episode is not None:
        return MediaType.TV

    # If it has only an episode number, assume TV (unless it was tagged anime)
    if parsed.episode is not None:
        return MediaType.TV

    # Movie heuristic:
    # If there's no season/episode info at all, treat as Movie.
    # This allows year lookup for "title-only" files like "5 Centimeters Per Second.mp4".
    return MediaType.MOVIE if parsed.title else MediaType.UNKNOWN
