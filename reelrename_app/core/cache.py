from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class YearCache:
    """
    In-memory cache to avoid repeated lookups.
    (Later we can persist this to disk.)
    """
    movie_year: Dict[str, int]

    def __init__(self) -> None:
        self.movie_year = {}

    def get_movie_year(self, title: str) -> Optional[int]:
        return self.movie_year.get(title.lower().strip())

    def set_movie_year(self, title: str, year: int) -> None:
        self.movie_year[title.lower().strip()] = year
