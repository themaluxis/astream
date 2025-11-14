from typing import List, Optional, Dict, Any

from astream.utils.http_client import http_client, BaseClient
from astream.scrapers.animesama.catalog import AnimeSamaCatalog
from astream.scrapers.animesama.details import AnimeSamaDetails
from astream.config.settings import settings


# ===========================
# Classe AnimeSamaAPI
# ===========================
class AnimeSamaAPI(BaseClient):

    def __init__(self):
        super().__init__()
        self.base_url = settings.ANIMESAMA_URL
        self.client = http_client

        self.catalog = AnimeSamaCatalog(http_client)
        self.details = AnimeSamaDetails(http_client)

    async def get_homepage_content(self) -> List[Dict[str, Any]]:

        return await self.catalog.get_homepage_content()

    async def search_anime(self, query: str, language: Optional[str] = None, genre: Optional[str] = None) -> List[Dict[str, Any]]:

        return await self.catalog.search_anime(query, language, genre)

    async def get_anime_details(self, anime_slug: str) -> Optional[Dict[str, Any]]:

        return await self.details.get_anime_details(anime_slug)

    async def get_seasons(self, anime_slug: str) -> List[Dict[str, Any]]:

        return await self.details.get_seasons(anime_slug)

    async def get_film_title(self, anime_slug: str, episode_num: int) -> Optional[str]:
        return await self.details.get_film_title(anime_slug, episode_num)


# ===========================
# Instance Singleton Globale
# ===========================
animesama_api = AnimeSamaAPI()
