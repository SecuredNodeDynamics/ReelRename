from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass(frozen=True)
class TmdbMovieResult:
    title: str
    year: Optional[int]
    tmdb_id: int


class TmdbClient:
    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("TMDB_API_KEY")
        self.base_url = "https://api.themoviedb.org/3"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def search_movie(self, query: str) -> Optional[TmdbMovieResult]:
        if not self.api_key:
            return None

        url = f"{self.base_url}/search/movie"
        params = {
            "api_key": self.api_key,
            "query": query,
            "include_adult": "false",
        }
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        results = data.get("results") or []
        if not results:
            return None

        best = results[0]
        release_date = best.get("release_date") or ""
        year = int(release_date[:4]) if len(release_date) >= 4 and release_date[:4].isdigit() else None

        return TmdbMovieResult(
            title=best.get("title") or query,
            year=year,
            tmdb_id=int(best["id"]),
        )
