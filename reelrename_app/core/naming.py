from __future__ import annotations

from reelrename_app.core.classifier import MediaType
from reelrename_app.core.parser import ParsedMedia


def proposed_name(parsed: ParsedMedia, media_type: MediaType, ext: str) -> str:
    """
    Conservative naming for v2 preview:
      - Movies: Title (Year).ext  (if year known)
      - TV: Show Name - SxxEyy.ext
      - Anime: Series Name - Exx.ext
      - Unknown: title-ish + ext
    """
    title = parsed.title or "Unknown Title"

    if media_type == MediaType.MOVIE:
        if parsed.year:
            return f"{title} ({parsed.year}){ext}"
        return f"{title}{ext}"

    if media_type == MediaType.TV:
        if parsed.season is not None and parsed.episode is not None:
            return f"{title} - S{parsed.season:02d}E{parsed.episode:02d}{ext}"
        if parsed.episode is not None:
            return f"{title} - E{parsed.episode:02d}{ext}"
        return f"{title}{ext}"

    if media_type == MediaType.ANIME:
        if parsed.episode is not None:
            return f"{title} - E{parsed.episode:02d}{ext}"
        return f"{title}{ext}"

    return f"{title}{ext}"
