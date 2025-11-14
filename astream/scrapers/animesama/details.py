from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup

from astream.utils.http_client import HttpClient
from astream.utils.logger import logger
from astream.scrapers.base import BaseScraper
from astream.utils.database import LockAcquisitionError
from astream.config.settings import settings
from astream.scrapers.animesama.parser import (
    parse_anime_details_from_html,
    parse_languages_from_html,
    parse_seasons_from_html,
    parse_film_titles_from_html
)
from astream.utils.cache import CacheKeys, CacheManager


# ===========================
# Classe AnimeSamaDetails
# ===========================
class AnimeSamaDetails(BaseScraper):

    def __init__(self, client: HttpClient):
        super().__init__(client, settings.ANIMESAMA_URL)

    async def get_anime_details(self, anime_slug: str) -> Optional[Dict[str, Any]]:
        try:
            logger.debug(f"ANIMESAMA: Récupération détails pour {anime_slug}")
            response = await self._internal_request('get', f"{self.base_url}/catalogue/{anime_slug}/")
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            anime_data = parse_anime_details_from_html(soup, anime_slug)

            anime_data["languages"] = parse_languages_from_html(response.text)

            return anime_data

        except Exception as e:
            logger.error(f"Échec détails pour {anime_slug}: {e}")
            return None

    async def get_seasons(self, anime_slug: str) -> List[Dict[str, Any]]:
        try:
            logger.debug(f"ANIMESAMA: Récupération saisons pour {anime_slug}")
            response = await self._internal_request('get', f"{self.base_url}/catalogue/{anime_slug}/")
            response.raise_for_status()

            seasons = parse_seasons_from_html(response.text, anime_slug, self.base_url)
            return seasons

        except Exception as e:
            logger.error(f"Échec saisons pour {anime_slug}: {e}")
            return []

    async def get_film_title(self, anime_slug: str, episode_num: int) -> Optional[str]:
        try:
            film_url = f"{self.base_url}/catalogue/{anime_slug}/film/vostfr/"

            response = await self._internal_request('get', film_url)
            response.raise_for_status()
            html = response.text

            film_titles = parse_film_titles_from_html(html)

            logger.debug(f"Titres films trouvés: {film_titles}")

            if film_titles and episode_num > 0 and episode_num <= len(film_titles):
                film_title = film_titles[episode_num - 1].strip()
                logger.debug(f"Titre film sélectionné: '{film_title}'")
                return film_title
            else:
                logger.warning(f"Épisode #{episode_num} invalide ou > nombre films ({len(film_titles)})")
                return None

        except Exception as e:
            logger.error(f"Erreur titre film {anime_slug} #{episode_num}: {e}")
            return None

    async def fetch_complete_anime_data(self, anime_slug: str) -> Optional[Dict[str, Any]]:
        anime_data = await self.get_anime_details(anime_slug)
        if not anime_data:
            return None

        seasons = await self.get_seasons(anime_slug)
        anime_data["seasons"] = seasons

        return anime_data


async def get_or_fetch_anime_details(animesama_details: AnimeSamaDetails, anime_slug: str) -> Optional[Dict[str, Any]]:
    cache_key = CacheKeys.anime_details(anime_slug)
    lock_key = f"metadata_fetch_{anime_slug}"

    try:
        return await CacheManager.get_or_fetch(
            cache_key=cache_key,
            fetch_func=lambda: animesama_details.fetch_complete_anime_data(anime_slug),
            lock_key=lock_key
        )
    except LockAcquisitionError:
        logger.warning(f"Verrou impossible {anime_slug}, tentative sans verrou")

        # Vérifier d'abord le cache (un autre thread a peut-être mis à jour)
        cached = await CacheManager.get(cache_key)
        if cached:
            logger.debug(f"Cache trouvé après timeout verrou: {anime_slug}")
            return cached

        # Si toujours pas en cache, scraper et sauvegarder
        anime_data = await animesama_details.fetch_complete_anime_data(anime_slug)
        if anime_data:
            await CacheManager.set(cache_key, anime_data)
        return anime_data
    except Exception as e:
        logger.error(f"Erreur inattendue détails {anime_slug}: {e}")
        return None
