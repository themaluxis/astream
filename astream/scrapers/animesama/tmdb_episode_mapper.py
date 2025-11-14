from typing import Dict, List
from datetime import datetime
from astream.utils.logger import logger
from astream.config.settings import SPECIAL_SEASON_THRESHOLD


# ===========================
# Classe AnimeSamaTMDBEpisodeMapper
# ===========================
class AnimeSamaTMDBEpisodeMapper:

    def __init__(self):
        self.tmdb_episodes = {}
        self.anime_sama_structure = {}

    def set_tmdb_episodes(self, tmdb_episodes_map: Dict[str, Dict]):
        self.tmdb_episodes = tmdb_episodes_map

    def set_anime_sama_structure(self, seasons_data: List[Dict]):
        self.anime_sama_structure = {}
        for season in seasons_data:
            season_num = season.get('season_number', 0)
            if season_num > 0:
                episode_count = season.get('episode_count', 0)
                if episode_count > 0:
                    self.anime_sama_structure[season_num] = episode_count

    def create_intelligent_mapping(self) -> Dict[str, Dict]:
        """
        Crée le mapping intelligent TMDB -> Anime-Sama avec vérification à 3 niveaux.
        Refuse le mapping si TMDB a moins d'épisodes, puis mappe séquentiellement les épisodes dans l'ordre chronologique.
        Algorithme complexe: filtrage air_date, construction queue TMDB, validation comptage, mapping 1:1.
        """
        if not self.anime_sama_structure or not self.tmdb_episodes:
            logger.log("TMDB", "Pas de données pour le mapping intelligent")
            return {}

        tmdb_by_season = {}
        today = datetime.now().strftime("%Y-%m-%d")

        for episode_key, episode_data in self.tmdb_episodes.items():
            if episode_key.startswith('s') and 'e' in episode_key:
                try:
                    season_part, episode_part = episode_key[1:].split('e')
                    season_num = int(season_part)
                    episode_num = int(episode_part)
                    if season_num <= 0:
                        continue
                    air_date = episode_data.get("air_date")
                    if air_date and air_date > today:
                        continue
                    elif not air_date:
                        continue

                    if season_num not in tmdb_by_season:
                        tmdb_by_season[season_num] = {}
                    tmdb_by_season[season_num][episode_num] = episode_data

                except ValueError:
                    continue

        # Créer une file d'attente séquentielle de tous les épisodes TMDB dans l'ordre chronologique
        episodes_queue = []
        for tmdb_season in sorted(tmdb_by_season.keys()):
            tmdb_episodes_season = tmdb_by_season[tmdb_season]

            for episode_num in sorted(tmdb_episodes_season.keys()):
                episodes_queue.append({
                    'tmdb_season': tmdb_season,
                    'tmdb_episode': episode_num,
                    'data': tmdb_episodes_season[episode_num]
                })

        total_tmdb_episodes = len(episodes_queue)

        anime_sama_episodes = []
        valid_seasons = {}
        for season_num, count in self.anime_sama_structure.items():
            if 0 < season_num < SPECIAL_SEASON_THRESHOLD:
                valid_seasons[season_num] = count

        total_anime_sama_episodes = sum(valid_seasons.values())

        # Vérification à 3 niveaux: refuse le mapping si TMDB a moins d'épisodes
        if total_tmdb_episodes < total_anime_sama_episodes:
            logger.log("TMDB", f"MAPPING INTERDIT: TMDB {total_tmdb_episodes} < Anime-Sama {total_anime_sama_episodes} (manque {total_anime_sama_episodes - total_tmdb_episodes})")
            return {}
        elif total_tmdb_episodes > total_anime_sama_episodes:
            logger.log("TMDB", f"MAPPING PARTIEL: TMDB {total_tmdb_episodes} > Anime-Sama {total_anime_sama_episodes} (surplus {total_tmdb_episodes - total_anime_sama_episodes})")
        else:
            logger.log("TMDB", f"MATCH PARFAIT: TMDB {total_tmdb_episodes} = Anime-Sama {total_anime_sama_episodes}")

        for anime_sama_season in sorted(valid_seasons.keys()):
            episode_count = valid_seasons[anime_sama_season]

            for anime_sama_episode in range(1, episode_count + 1):
                anime_sama_episodes.append({
                    'season': anime_sama_season,
                    'episode': anime_sama_episode,
                    'key': f"s{anime_sama_season}e{anime_sama_episode}"
                })

        intelligent_mapping = {}

        episodes_to_map = min(len(anime_sama_episodes), len(episodes_queue))

        for i in range(episodes_to_map):
            anime_sama_ep = anime_sama_episodes[i]
            tmdb_ep = episodes_queue[i]
            anime_sama_key = anime_sama_ep['key']
            intelligent_mapping[anime_sama_key] = tmdb_ep['data']

        return intelligent_mapping


# ===========================
# Mapping intelligent des épisodes
# ===========================
def create_intelligent_episode_mapping(
    tmdb_episodes_map: Dict[str, Dict],
    seasons_data: List[Dict],
    episodes_map: Dict[int, int]
) -> Dict[str, Dict]:
    """
    Crée un mapping chronologique 1:1 entre épisodes TMDB et Anime-Sama.
    Refuse le mapping si TMDB a moins d'épisodes (sécurité).
    """
    mapper = AnimeSamaTMDBEpisodeMapper()

    mapper.set_tmdb_episodes(tmdb_episodes_map)

    anime_sama_structure = []
    for season in seasons_data:
        season_num = season.get('season_number', 0)
        if season_num > 0:
            episode_count = episodes_map.get(season_num, 0)
            if episode_count > 0:
                season_data = season.copy()
                season_data['episode_count'] = episode_count
                anime_sama_structure.append(season_data)

    mapper.set_anime_sama_structure(anime_sama_structure)
    result = mapper.create_intelligent_mapping()

    return result
