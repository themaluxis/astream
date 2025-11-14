import re
import unicodedata
import asyncio
from typing import Optional, Dict, List, Any
from difflib import SequenceMatcher

from astream.utils.http_client import HttpClient, safe_json_decode
from astream.utils.cache import CacheManager, cache_stats
from astream.utils.logger import logger
from astream.config.settings import settings, TMDB_ANIMATION_GENRE_ID


# ===========================
# Normalisation des titres
# ===========================
def normalize_title(title: str, for_search: bool = False) -> str:
    if not title:
        return ""

    title = title.strip()

    # Si mode recherche, retirer les suffixes communs
    if for_search:
        title = title.replace(" OAV", "").replace(" OVA", "")
        title = title.replace(" Movie", "").replace(" Film", "")
        title = " ".join(title.split())
        return title.strip()

    # Normalisation complète pour comparaison
    title = title.lower()
    title = unicodedata.normalize('NFD', title)
    title = ''.join(char for char in title if unicodedata.category(char) != 'Mn')
    title = re.sub(r'[^\w\s]', '', title)
    title = re.sub(r'\s+', ' ', title)
    title = title.strip()

    return title


# ===========================
# Calcul de similarité
# ===========================
def calculate_similarity(title1: str, title2: str) -> float:
    if not title1 or not title2:
        return 0.0

    norm1 = normalize_title(title1)
    norm2 = normalize_title(title2)

    if norm1 == norm2:
        return 100.0

    no_space1 = norm1.replace(' ', '')
    no_space2 = norm2.replace(' ', '')
    if no_space1 == no_space2:
        return 95.0

    similarity = SequenceMatcher(None, norm1, norm2).ratio()
    return min(similarity * 90, 90.0)


# ===========================
# Récupération des titres TMDB
# ===========================
async def get_all_tmdb_titles(tmdb_client, tmdb_id: int, media_type: str) -> List[str]:

    if not tmdb_client.api_key:
        return []

    try:
        endpoint = "tv" if media_type == "tv" else "movie"
        url = f"{tmdb_client.base_url}/{endpoint}/{tmdb_id}"
        params = {
            "api_key": tmdb_client.api_key,
            "language": "fr-FR",
            "append_to_response": "alternative_titles"
        }

        response = await tmdb_client.client.get(url, params=params)
        data = safe_json_decode(response, f"TMDB pour ID {tmdb_id}", default=None)
        if not data:
            return []

        all_titles = set()
        main_title = data.get("name") or data.get("title")
        if main_title:
            all_titles.add(main_title.strip())

        original_title = data.get("original_name") or data.get("original_title")
        if original_title:
            all_titles.add(original_title.strip())

        origin_countries = data.get("origin_country", [])
        if not origin_countries and media_type == "movie":
            production_countries = data.get("production_countries", [])
            origin_countries = [country.get("iso_3166_1") for country in production_countries if country.get("iso_3166_1")]

        alternative_titles = data.get("alternative_titles") or {}
        titles_list = alternative_titles.get("results", []) if media_type == "tv" else alternative_titles.get("titles", [])

        for title_data in titles_list:
            iso_country = title_data.get("iso_3166_1", "")
            title = title_data.get("title", "").strip()

            if not title:
                continue

            if iso_country == "FR":
                all_titles.add(title)

            elif iso_country in {"US", "GB"}:
                all_titles.add(title)

            elif iso_country in origin_countries:
                all_titles.add(title)

            elif not iso_country:
                all_titles.add(title)

        final_titles = [title for title in all_titles if title and len(title.strip()) > 0]

        logger.debug(f"Récupéré {len(final_titles)} titres TMDB pour ID {tmdb_id}")
        return final_titles

    except Exception as e:
        logger.error(f"Erreur récupération titres alternatifs TMDB {tmdb_id}: {e}")
        return []


# ===========================
# Recherche de la meilleure correspondance
# ===========================
async def find_best_match(anime_title: str, tmdb_results: List[Dict[str, Any]], tmdb_client) -> Optional[Dict[str, Any]]:
    if not tmdb_results:
        return None

    if len(tmdb_results) == 1:
        return tmdb_results[0]

    async def get_titles_for_result(result):
        tmdb_id = result.get("id")
        media_type = "tv" if "name" in result else "movie"
        all_tmdb_titles = await get_all_tmdb_titles(tmdb_client, tmdb_id, media_type)

        if not all_tmdb_titles:
            all_tmdb_titles = []
            main_title = result.get("name") or result.get("title")
            if main_title:
                all_tmdb_titles.append(main_title)
            original_title = result.get("original_name") or result.get("original_title")
            if original_title and original_title != main_title:
                all_tmdb_titles.append(original_title)

        return result, all_tmdb_titles

    titles_tasks = [get_titles_for_result(result) for result in tmdb_results]
    results_with_titles = await asyncio.gather(*titles_tasks, return_exceptions=True)

    best_match = None
    best_score = 0.0

    for item in results_with_titles:
        if isinstance(item, Exception):
            logger.warning(f"Erreur lors de la récupération des titres TMDB: {item}")
            continue

        result, all_tmdb_titles = item
        max_score = 0.0

        for tmdb_title in all_tmdb_titles:
            score = calculate_similarity(anime_title, tmdb_title)
            if score > max_score:
                max_score = score

        if max_score > best_score:
            best_score = max_score
            best_match = result

    if best_match:
        final_name = best_match.get("name") or best_match.get("title", "")
        logger.debug(f"TMDB match trouvé: {final_name} ({best_score:.1f}%)")

    return best_match


# ===========================
# Classe TMDBClient
# ===========================
class TMDBClient:

    def __init__(self, client: HttpClient, api_key: Optional[str] = None):
        self.client = client
        self.api_key = api_key or settings.TMDB_API_KEY
        self.base_url = "https://api.themoviedb.org/3"
        self.image_base_url = "https://image.tmdb.org/t/p"

    async def search_anime(self, title: str) -> Optional[Dict[str, Any]]:

        cache_key = f"tmdb:search:{title.lower()}"
        lock_key = f"lock:tmdb:search:{title.lower()}"

        if not self.api_key:
            logger.warning("Aucune clé API TMDB configurée")
            return None

        async def fetch_tmdb_search():
            cache_stats.record_miss("TMDB Search")
            url = f"{self.base_url}/search/tv"
            params = {
                "api_key": self.api_key,
                "query": title,
                "language": "fr-FR"
            }

            response = await self.client.get(url, params=params)
            data = safe_json_decode(response, f"TMDB search pour '{title}'", default=None)
            if not data or "results" not in data:
                return None

            results = data["results"]

            animation_results = []
            if results:
                for result in results:
                    genre_ids = result.get("genre_ids", [])
                    if TMDB_ANIMATION_GENRE_ID in genre_ids:
                        animation_results.append(result)

            if not animation_results:
                movie_url = f"{self.base_url}/search/movie"
                movie_response = await self.client.get(movie_url, params=params)
                movie_data = safe_json_decode(movie_response, f"TMDB movie search pour '{title}'", default=None)
                if movie_data and "results" in movie_data:
                    movie_results = movie_data["results"]
                    for result in movie_results:
                        genre_ids = result.get("genre_ids", [])
                        if TMDB_ANIMATION_GENRE_ID in genre_ids:
                            animation_results.append(result)

                if not animation_results:
                    logger.debug(f"Aucun résultat TMDB pour: {title}")
                    return None

            best_match = await find_best_match(title, animation_results, self)
            if not best_match:
                return None

            if "name" in best_match:
                best_match["media_type"] = "tv"
            else:
                best_match["media_type"] = "movie"

            return best_match

        try:
            cached_data = await CacheManager.get_or_fetch(
                cache_key=cache_key,
                fetch_func=fetch_tmdb_search,
                lock_key=lock_key,
                ttl=settings.TMDB_TTL
            )

            if cached_data:
                cache_stats.record_hit("TMDB Search")

            return cached_data

        except Exception as e:
            logger.error(f"Erreur recherche TMDB pour '{title}': {e}")
            return None

    async def get_anime_details(self, tmdb_id: int, media_type: str = "tv") -> Optional[Dict[str, Any]]:

        cache_key = f"tmdb:{tmdb_id}"
        lock_key = f"lock:tmdb:{tmdb_id}"

        if not self.api_key:
            return None

        async def fetch_tmdb_details():
            cache_stats.record_miss("TMDB Details")
            endpoint = "tv" if media_type == "tv" else "movie"
            url = f"{self.base_url}/{endpoint}/{tmdb_id}"
            params = {
                "api_key": self.api_key,
                "language": "fr-FR",
                "append_to_response": "videos,images,credits,external_ids",
                "include_image_language": "fr,en,null"
            }

            response = await self.client.get(url, params=params)
            data = safe_json_decode(response, f"TMDB détails pour ID {tmdb_id}", default=None)
            if not data:
                return None

            return data

        try:
            cached_data = await CacheManager.get_or_fetch(
                cache_key=cache_key,
                fetch_func=fetch_tmdb_details,
                lock_key=lock_key,
                ttl=settings.TMDB_TTL
            )

            if cached_data:
                cache_stats.record_hit("TMDB Details")

            return cached_data

        except Exception as e:
            logger.error(f"Erreur détails TMDB pour ID {tmdb_id}: {e}")
            return None

    async def get_season_details(self, tmdb_id: int, season_number: int) -> Optional[Dict[str, Any]]:

        cache_key = f"tmdb:{tmdb_id}:s{season_number}"
        lock_key = f"lock:tmdb:{tmdb_id}:s{season_number}"

        if not self.api_key:
            return None

        async def fetch_season_details():
            cache_stats.record_miss("TMDB Seasons")
            url = f"{self.base_url}/tv/{tmdb_id}/season/{season_number}"
            params = {
                "api_key": self.api_key,
                "language": "fr-FR"
            }

            response = await self.client.get(url, params=params)
            data = safe_json_decode(response, f"TMDB saison {tmdb_id}:S{season_number}", default=None)
            if not data:
                return None

            return data

        try:
            cached_data = await CacheManager.get_or_fetch(
                cache_key=cache_key,
                fetch_func=fetch_season_details,
                lock_key=lock_key,
                ttl=settings.TMDB_TTL
            )

            if cached_data:
                cache_stats.record_hit("TMDB Seasons")

            return cached_data

        except Exception as e:
            logger.error(f"Erreur saison TMDB {tmdb_id}:S{season_number}: {e}")
            return None

    def _get_image_url(self, path: str, size: str = "w500") -> str:

        if not path:
            return ""
        return f"{self.image_base_url}/{size}{path}"

    def _get_poster_url(self, path: str) -> str:

        return self._get_image_url(path, "original")

    def _get_backdrop_url(self, path: str) -> str:

        return self._get_image_url(path, "original")

    def _get_logo_url(self, path: str) -> str:

        return self._get_image_url(path, "original")

    def get_episode_image_url(self, path: str) -> str:
        return self._get_image_url(path, "original")

    def _extract_trailer_id(self, videos_data: Dict[str, Any]) -> Optional[str]:

        if not videos_data:
            return None

        video_list = videos_data.get("results", videos_data) if isinstance(videos_data, dict) else videos_data

        if not isinstance(video_list, list):
            return None

        for video in video_list:
            if (video.get("type") == "Trailer" and
                    video.get("site") == "YouTube"):
                return video.get("key")
        return None
