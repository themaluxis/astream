from typing import Dict, Any, Optional, Tuple


# ===========================
# Classe SeasonMapper
# ===========================
class SeasonMapper:

    @staticmethod
    def map_episode_to_path(episode_number: int, season_data: Dict[str, Any]) -> Optional[Tuple[str, int]]:
        main_path = season_data.get("path", "")
        main_episode_count = season_data.get("episode_count", 0)

        if episode_number <= main_episode_count:
            return (main_path, episode_number)

        sub_seasons = season_data.get("sub_seasons", [])
        if not sub_seasons:
            return None

        remaining_episodes = episode_number - main_episode_count

        for sub_season in sub_seasons:
            sub_episode_count = sub_season.get("episode_count", 0)

            if remaining_episodes <= sub_episode_count:
                return (sub_season.get("path", ""), remaining_episodes)

            remaining_episodes -= sub_episode_count

        return None
