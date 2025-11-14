import re
import asyncio
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

from astream.utils.logger import logger
from astream.scrapers.base import BaseScraper
from astream.utils.cache import CacheManager
from astream.config.settings import settings, LANGUAGES_TO_CHECK
from astream.scrapers.animesama.special_episodes import special_episodes_detector
from astream.utils.filters import filter_excluded_domains
from astream.utils.languages import filter_by_language, sort_by_language_priority
from astream.scrapers.animesama.season_mapper import SeasonMapper


# ===========================
# Aide : Construire l'URL de saison
# ===========================
def _build_season_url(base_url: str, anime_slug: str, season_path: str, language: str) -> str:
    return f"{base_url}/catalogue/{anime_slug}/{season_path}/{language}/"


# ===========================
# Classe AnimeSamaPlayerExtractor
# ===========================
class AnimeSamaPlayerExtractor(BaseScraper):

    def __init__(self, client):
        super().__init__(client, settings.ANIMESAMA_URL)

    async def extract_player_urls_smart_mapping_with_language(self, anime_slug: str, season_data: Dict[str, Any], episode_number: int, language_filter: Optional[str] = None, config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        season_num = season_data.get('season_number')
        cache_key = f"as:{anime_slug}:s{season_num}e{episode_number}"
        lock_key = f"lock:players:{anime_slug}:s{season_num}e{episode_number}"

        user_language_order = "VOSTFR,VF"
        if config and "languageOrder" in config:
            user_language_order = config["languageOrder"]

        try:
            # Récupération players avec DistributedLock pour éviter race conditions
            async def fetch_player_urls():
                logger.log("DATABASE", f"Cache miss {cache_key} - Extraction players")

                # PARALLÉLISATION : Extraire les players de toutes les langues en parallèle pour éviter N+1 queries
                async def extract_for_language(language):
                    try:
                        urls = await self._extract_from_single_season(anime_slug, season_data, episode_number, language, config)
                        return language, urls
                    except Exception as e:
                        logger.warning(f"Erreur extraction langue {language}: {e}")
                        return language, []

                # Récupération parallèle pour toutes les langues
                language_tasks = [extract_for_language(lang) for lang in LANGUAGES_TO_CHECK]
                results = await asyncio.gather(*language_tasks, return_exceptions=True)

                player_urls_with_language = []
                for item in results:
                    if isinstance(item, Exception):
                        logger.warning(f"Erreur lors de l'extraction des players: {item}")
                        continue

                    language, urls = item
                    for url in urls:
                        player_urls_with_language.append({
                            "url": url,
                            "language": language
                        })

                cache_data = {
                    "player_urls": player_urls_with_language,
                    "anime_slug": anime_slug,
                    "season": season_num,
                    "episode": episode_number,
                    "language_filter": language_filter,
                    "total_players": len(player_urls_with_language)
                }
                logger.log("DATABASE", f"Cache set {cache_key} - {len(player_urls_with_language)} players")
                return cache_data

            cached_players = await CacheManager.get_or_fetch(
                cache_key=cache_key,
                fetch_func=fetch_player_urls,
                lock_key=lock_key,
                ttl=settings.EPISODE_TTL
            )

            player_urls = cached_players.get("player_urls", []) if cached_players else []
            filtered_urls = filter_by_language(player_urls, language_filter)

            if (not language_filter or language_filter == "Tout") and user_language_order != "VOSTFR,VF":
                filtered_urls = sort_by_language_priority(filtered_urls, user_language_order)

            return filtered_urls

        except Exception as e:
            logger.error(f"Erreur mapping intelligent: {e}")
            return []

    async def _extract_from_single_season(self, anime_slug: str, season_data: Dict[str, Any], episode_number: int, language: str, config: Optional[Dict[str, Any]] = None) -> List[str]:
        try:
            # Utilisation de SeasonMapper pour obtenir le bon path et épisode number
            season_path = season_data.get("path", "")
            main_url = _build_season_url(self.base_url, anime_slug, season_path, language)

            # Obtenir le nombre d'épisodes de la saison principale
            main_season_episode_count = await self._get_episode_count_from_url(main_url)

            # Mettre à jour season_data avec le compte d'épisodes pour SeasonMapper
            season_data_with_count = {
                **season_data,
                "episode_count": main_season_episode_count
            }

            # Utiliser SeasonMapper pour mapper l'épisode au bon path
            mapping_result = SeasonMapper.map_episode_to_path(episode_number, season_data_with_count)

            if not mapping_result:
                logger.warning(f"Impossible de mapper épisode {episode_number} en {language}")
                return []

            target_path, target_episode_number = mapping_result
            target_url = _build_season_url(self.base_url, anime_slug, target_path, language)

            response = await self._internal_request('get', target_url)
            response.raise_for_status()
            html = response.text

            episode_urls = await self._extract_from_episodes_js(target_url, html, target_episode_number)

            episode_urls = filter_excluded_domains(episode_urls, config.get('userExcludedDomains', '') if config else '')

            return episode_urls

        except Exception as e:
            logger.error(f"Erreur extraction: {e}")
            return []

    async def _extract_from_episodes_js(self, season_url: str, html: str, episode_number: int) -> List[str]:
        try:
            player_urls = []

            episodes_js_match = re.search(r'episodes\.js\?filever=\d+', html)

            if not episodes_js_match:
                return []

            episodes_js_filename = episodes_js_match.group(0)
            season_base_url = season_url.rstrip('/') + '/'
            episodes_js_url = season_base_url + episodes_js_filename

            response = await self._internal_request('get', episodes_js_url)
            response.raise_for_status()
            js_content = response.text

            # Capturer tous les arrays eps (supporte multilignes)
            all_eps_matches = re.findall(r'var\s+eps\w*\s*=\s*\[([\s\S]*?)\];', js_content)
            if not all_eps_matches:
                logger.warning("Aucun array eps dans episodes.js")
                return []

            for eps_content in all_eps_matches:
                url_matches = re.findall(r"['\"]([^'\"]+)['\"]", eps_content)
                valid_urls = [url for url in url_matches if url and "://" in url]

                if valid_urls:
                    filter_result = special_episodes_detector.filter_special_episodes(valid_urls, html)
                    filtered_urls = filter_result["filtered_urls"]

                    if episode_number > 0 and len(filtered_urls) >= episode_number and filtered_urls[episode_number - 1]:
                        episode_url = filtered_urls[episode_number - 1]

                        if episode_url and episode_url.strip() and self._is_video_player_url(episode_url):
                            if not episode_url.startswith('http'):
                                episode_url = urljoin(season_base_url, episode_url)

                            player_urls.append(episode_url)

            return player_urls

        except Exception as e:
            logger.error(f"Erreur extraction episodes.js: {e}")
            return []

    async def _get_episode_count_from_url(self, season_url: str) -> int:
        """
        Détermine le nombre d'épisodes disponibles dans une saison.
        Compte tous les épisodes puis soustrait les épisodes spéciaux.
        """
        try:
            response = await self._internal_request('get', season_url)
            response.raise_for_status()
            html = response.text

            episodes_js_match = re.search(r'episodes\.js\?filever=\d+', html)

            if not episodes_js_match:
                return 0

            episodes_js_filename = episodes_js_match.group(0)
            season_base_url = season_url.rstrip('/') + '/'
            episodes_js_url = season_base_url + episodes_js_filename

            # Récupérer le fichier episodes.js et compter les épisodes
            response = await self._internal_request('get', episodes_js_url)
            response.raise_for_status()
            js_content = response.text

            # Compter tous les épisodes dans les arrays
            all_eps_matches = re.findall(r'var\s+eps\w*\s*=\s*\[([\s\S]*?)\];', js_content)
            max_episodes = 0

            for eps_content in all_eps_matches:
                url_matches = re.findall(r"['\"]([^'\"]+)['\"]", eps_content)
                valid_urls = [url for url in url_matches if url and "://" in url and self._is_video_player_url(url)]

                if len(valid_urls) > max_episodes:
                    max_episodes = len(valid_urls)

            # Soustraire les épisodes spéciaux si détectés
            episode_count = max_episodes

            try:
                analysis = special_episodes_detector.analyze_javascript_structure(html)
                special_count = len(analysis.get("special_episodes", []))

                if special_count > 0:
                    episode_count = max_episodes - special_count
                    logger.debug(f"Comptage: {max_episodes} total - {special_count} SP = {episode_count} épisodes normaux")
                else:
                    logger.debug(f"Comptage: {max_episodes} épisodes (pas de SP détecté)")

            except Exception as e:
                # Si erreur dans la détection des SP, garder le total brut
                logger.debug(f"Erreur détection SP ({e}), comptage: {max_episodes} épisodes")
                pass

            return episode_count

        except Exception as e:
            logger.warning(f"Erreur comptage épisodes: {e}")
            return 0

    def _is_video_player_url(self, url: str) -> bool:

        if not url or not url.strip():
            return False

        if not url.startswith('http'):
            return False

        excluded_extensions = ['.js', '.css', '.png', '.jpg', '.svg', '.woff', '.ico', '.gif', '.jpeg']
        url_lower = url.lower()

        for ext in excluded_extensions:
            if ext in url_lower:
                return False

        excluded_patterns = [
            '/public/',
            '/static/',
            f'{settings.ANIMESAMA_URL.replace("https://", "").replace("http://", "")}/catalogue/',
            '#'
        ]

        for pattern in excluded_patterns:
            if pattern in url:
                return False

        return True
