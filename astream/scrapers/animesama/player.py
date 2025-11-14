import asyncio
from typing import List, Optional, Dict, Any

from astream.utils.logger import logger
from astream.scrapers.base import BaseScraper
from astream.scrapers.animesama.player_extractor import AnimeSamaPlayerExtractor
from astream.scrapers.animesama.video_resolver import AnimeSamaVideoResolver
from astream.config.settings import settings, LANGUAGES_TO_CHECK
from astream.utils.stremio_helpers import format_stream_for_stremio
from astream.utils.http_client import http_client


# ===========================
# Classe AnimeSamaPlayer
# ===========================
class AnimeSamaPlayer(BaseScraper):

    def __init__(self):
        super().__init__(http_client, settings.ANIMESAMA_URL)
        self.extractor = AnimeSamaPlayerExtractor(http_client)
        self.resolver = AnimeSamaVideoResolver(http_client)

    async def get_episode_streams(self, anime_slug: str, season_data: Dict[str, Any], episode_number: int, language_filter: Optional[str] = None, config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:

        logger.log("STREAM", f"Génération streams temps réel {anime_slug} S{season_data.get('season_number')}E{episode_number}")

        try:
            logger.log("STREAM", f"Récupération streams {anime_slug} S{season_data.get('season_number')}E{episode_number}")

            player_urls_with_language = await self.extractor.extract_player_urls_smart_mapping_with_language(
                anime_slug, season_data, episode_number, language_filter, config
            )

            if not player_urls_with_language:
                logger.warning(f"Aucun player trouvé {anime_slug} S{season_data.get('season_number')}E{episode_number}")
                return []

            video_urls_with_language = await self.resolver.extract_video_urls_from_players_with_language(
                player_urls_with_language
            )

            streams = []
            season_num = season_data.get('season_number')

            for video_data in video_urls_with_language:
                video_url = video_data["url"]
                detected_language = video_data["language"] or "VOSTFR"

                streams.append(
                    format_stream_for_stremio(video_url, detected_language, anime_slug, season_num)
                )

            logger.log("STREAM", f"Trouvé {len(streams)} streams {anime_slug} S{season_num}E{episode_number}")
            return streams

        except Exception as e:
            logger.error(f"Erreur récupération streams: {e}")
            return []

    async def get_available_episodes_count(self, anime_slug: str, season_data: Dict[str, Any]) -> Dict[str, int]:

        try:
            logger.debug(f"Comptage épisodes {anime_slug} S{season_data.get('season_number')}")

            episode_counts = {}

            async def count_for_language_with_sub_seasons(language: str) -> tuple[str, int]:
                try:
                    season_path = season_data.get("path", "")
                    main_season_url = f"{self.base_url}/catalogue/{anime_slug}/{season_path}/{language.lower()}/"

                    main_count = await self.extractor._get_episode_count_from_url(main_season_url)

                    total_count = main_count
                    for sub_season in season_data.get("sub_seasons", []):
                        sub_path = sub_season.get("path", "")
                        if sub_path:
                            sub_url = f"{self.base_url}/catalogue/{anime_slug}/{sub_path}/{language.lower()}/"
                            try:
                                sub_count = await self.extractor._get_episode_count_from_url(sub_url)
                                if sub_count > 0:
                                    total_count += sub_count
                            except Exception as e:
                                logger.debug(f"Erreur sous-saison {sub_path} ({language}): {e}")
                                continue

                    return language, total_count

                except Exception as e:
                    logger.warning(f"Erreur comptage langue {language}: {e}")
                    return language, 0

            tasks = [count_for_language_with_sub_seasons(lang) for lang in LANGUAGES_TO_CHECK]
            results = await asyncio.gather(*tasks)

            for language, count in results:
                episode_counts[language] = count

            total_episodes = max(episode_counts.values()) if episode_counts and episode_counts.values() else 0
            vostfr_count = episode_counts.get('VOSTFR', 0)
            vf_count = episode_counts.get('VF', 0)
            logger.log("ANIMESAMA", f"Comptage S{season_data.get('season_number')}: {total_episodes} épisodes (VOSTFR: {vostfr_count}, VF: {vf_count})")

            return episode_counts

        except Exception as e:
            logger.error(f"Erreur comptage épisodes: {e}")
            return {}


# ===========================
# Instance Singleton Globale
# ===========================
animesama_player = AnimeSamaPlayer()
