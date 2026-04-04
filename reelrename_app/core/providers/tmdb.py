from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional, List

import requests


@dataclass(frozen=True)
class TmdbMovieResult:
    title: str
    year: Optional[int]
    tmdb_id: int


@dataclass(frozen=True)
class TmdbTvResult:
    title: str
    year: Optional[int]
    tmdb_id: int


@dataclass(frozen=True)
class TmdbEpisodeResult:
    episode_title: str
    season_number: int
    episode_number: int


@dataclass(frozen=True)
class TmdbSearchResult:
    title: str
    year: Optional[int]
    tmdb_id: int
    media_type: str  # "movie" | "tv"


class TmdbClient:
    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("TMDB_API_KEY")
        self.base_url = "https://api.themoviedb.org/3"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _build_search_result_from_detail(self, media_type: str, data: dict) -> Optional[TmdbSearchResult]:
        """Convert TMDb detail payload into TmdbSearchResult."""
        try:
            tmdb_id = int(data.get("id"))
        except Exception:
            return None

        if media_type == "movie":
            title = (data.get("title") or "").strip()
            date = data.get("release_date") or ""
        else:
            title = (data.get("name") or "").strip()
            date = data.get("first_air_date") or ""

        if not title:
            return None

        year = int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else None
        return TmdbSearchResult(title=title, year=year, tmdb_id=tmdb_id, media_type=media_type)

    def _fetch_by_id(self, media_type: str, tmdb_id: int) -> Optional[TmdbSearchResult]:
        if media_type not in ("movie", "tv"):
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/{media_type}/{tmdb_id}",
                params={"api_key": self.api_key, "language": "en-US"},
                timeout=10,
            )
            resp.raise_for_status()
            return self._build_search_result_from_detail(media_type, resp.json())
        except Exception:
            return None

    def _parse_tmdb_lookup_input(self, query: str) -> tuple[Optional[str], Optional[int]]:
        """Parse input into (media_type, id).

        Supports:
        - 249907
        - tv:249907 / movie:862
        - t:249907 / m:862
        - https://www.themoviedb.org/tv/249907-9004?language=en-US
        """
        q = (query or "").strip()
        if not q:
            return None, None

        # Full TMDb URL
        m = re.search(r"themoviedb\.org/(movie|tv)/(\d+)", q, re.IGNORECASE)
        if m:
            return m.group(1).lower(), int(m.group(2))

        # Prefixed type: tv:123, movie:123, t:123, m:123
        m = re.match(r"^(movie|tv|m|t)\s*[:#\-/ ]\s*(\d+)$", q, re.IGNORECASE)
        if m:
            mt = m.group(1).lower()
            media_type = "movie" if mt in ("movie", "m") else "tv"
            return media_type, int(m.group(2))

        # Raw numeric id
        if q.isdigit():
            return None, int(q)

        return None, None

    def search_multi(self, query: str, limit: int = 12) -> List[TmdbSearchResult]:
        """Search TMDb for both movies and TV shows and return ranked candidates.

        Also supports direct ID lookup from code/URL input.
        """
        if not self.api_key:
            return []

        q = (query or "").strip()
        if not q:
            return []

        # 1) Try direct TMDb ID lookup first (for code/URL input)
        media_hint, tmdb_id = self._parse_tmdb_lookup_input(q)
        if tmdb_id is not None:
            id_hits: List[TmdbSearchResult] = []
            if media_hint in ("movie", "tv"):
                hit = self._fetch_by_id(media_hint, tmdb_id)
                if hit:
                    id_hits.append(hit)
            else:
                # Unknown type for raw id: try TV first, then movie
                tv_hit = self._fetch_by_id("tv", tmdb_id)
                if tv_hit:
                    id_hits.append(tv_hit)
                movie_hit = self._fetch_by_id("movie", tmdb_id)
                if movie_hit:
                    id_hits.append(movie_hit)

            if id_hits:
                return id_hits[:max(1, limit)]

        out: List[TmdbSearchResult] = []

        def _append_movie_rows(data: dict) -> None:
            for row in (data.get("results") or []):
                title = (row.get("title") or "").strip()
                if not title:
                    continue
                release_date = row.get("release_date") or ""
                year = int(release_date[:4]) if len(release_date) >= 4 and release_date[:4].isdigit() else None
                out.append(TmdbSearchResult(
                    title=title,
                    year=year,
                    tmdb_id=int(row["id"]),
                    media_type="movie",
                ))

        def _append_tv_rows(data: dict) -> None:
            for row in (data.get("results") or []):
                title = (row.get("name") or "").strip()
                if not title:
                    continue
                first_air_date = row.get("first_air_date") or ""
                year = int(first_air_date[:4]) if len(first_air_date) >= 4 and first_air_date[:4].isdigit() else None
                out.append(TmdbSearchResult(
                    title=title,
                    year=year,
                    tmdb_id=int(row["id"]),
                    media_type="tv",
                ))

        try:
            movie_resp = requests.get(
                f"{self.base_url}/search/movie",
                params={"api_key": self.api_key, "query": q, "include_adult": "false"},
                timeout=10,
            )
            movie_resp.raise_for_status()
            _append_movie_rows(movie_resp.json())
        except Exception:
            pass

        try:
            tv_resp = requests.get(
                f"{self.base_url}/search/tv",
                params={"api_key": self.api_key, "query": q, "include_adult": "false"},
                timeout=10,
            )
            tv_resp.raise_for_status()
            _append_tv_rows(tv_resp.json())
        except Exception:
            pass

        # Prefer exact-ish title matches, then keep original API order.
        ql = q.lower()
        out.sort(key=lambda r: (0 if r.title.lower().startswith(ql) else 1, r.title.lower()))

        # Deduplicate same media_type + tmdb_id and trim.
        dedup: List[TmdbSearchResult] = []
        seen = set()
        for r in out:
            k = (r.media_type, r.tmdb_id)
            if k in seen:
                continue
            seen.add(k)
            dedup.append(r)
            if len(dedup) >= limit:
                break

        return dedup

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

    def search_tv(self, query: str) -> Optional[TmdbTvResult]:
        """Search for a TV show by name."""
        if not self.api_key:
            return None

        url = f"{self.base_url}/search/tv"
        params = {
            "api_key": self.api_key,
            "query": query,
            "include_adult": "false",
        }
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()

            results = data.get("results") or []
            if not results:
                return None

            best = results[0]
            first_air_date = best.get("first_air_date") or ""
            year = int(first_air_date[:4]) if len(first_air_date) >= 4 and first_air_date[:4].isdigit() else None

            return TmdbTvResult(
                title=best.get("name") or query,
                year=year,
                tmdb_id=int(best["id"]),
            )
        except Exception:
            return None

    def get_episode_details(self, tv_id: int, season: int, episode: int) -> Optional[TmdbEpisodeResult]:
        """Get episode details including episode title."""
        if not self.api_key:
            return None

        url = f"{self.base_url}/tv/{tv_id}/season/{season}/episode/{episode}"
        params = {
            "api_key": self.api_key,
        }
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()

            episode_title = data.get("name") or ""
            if not episode_title:
                return None

            return TmdbEpisodeResult(
                episode_title=episode_title,
                season_number=data.get("season_number", season),
                episode_number=data.get("episode_number", episode),
            )
        except Exception:
            return None
