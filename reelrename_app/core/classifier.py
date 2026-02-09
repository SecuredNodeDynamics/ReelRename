from __future__ import annotations

from enum import Enum
from reelrename_app.core.parser import ParsedMedia


class MediaType(str, Enum):
    MOVIE = "Movie"
    TV = "TV"
    ANIME = "Anime"
    ANIME_MOVIE = "Anime-Movie"
    UNKNOWN = "Unknown"


def classify(parsed: ParsedMedia) -> MediaType:
    # Anime with season/episode: TV Anime
    if parsed.is_anime:
        # Heuristic: If it has season/episode, it's a TV Anime
        if parsed.season is not None or parsed.episode is not None:
            return MediaType.ANIME
        # If it's anime, has a year, and no episode/season, treat as Anime-Movie
        if parsed.year is not None and parsed.season is None and parsed.episode is None:
            return MediaType.ANIME_MOVIE
        # Fallback: just Anime
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
