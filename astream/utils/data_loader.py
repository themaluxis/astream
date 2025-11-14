import os
import json
import asyncio
from typing import List, Dict, Any, Optional
from astream.utils.logger import logger
from astream.utils.http_client import HttpClient, safe_json_decode
from astream.config.settings import settings


# ===========================
# Classe DatasetLoader
# ===========================
class DatasetLoader:

    def __init__(self, http_client: HttpClient):
        self.http_client = http_client
        self.dataset_path = os.path.join("data", "dataset.json")
        self.dataset = {"anime": []}
        self._anime_dict = {}
        self._dataset_lock = asyncio.Lock()

    async def initialize(self):
        try:
            async with self._dataset_lock:
                if os.path.exists(self.dataset_path):
                    logger.log("DATASET", f"Dataset local trouvé: {self.dataset_path}")
                    self.dataset = self._load_local_dataset()
                else:
                    if settings.DATASET_ENABLED:
                        logger.log("DATASET", "Aucun dataset local - Téléchargement depuis GitHub")
                        await self._download_and_save_dataset()
                    else:
                        logger.log("DATASET", "Dataset désactivé - Utilisation dataset vide")
                        self.dataset = {"anime": []}
                self._build_search_cache()

            if settings.DATASET_ENABLED and settings.DATASET_UPDATE_INTERVAL > 0:
                asyncio.create_task(self._periodic_update())

            logger.log("DATASET", f"Initialisé avec {len(self.dataset.get('anime', []))} anime")

        except Exception as e:
            logger.error(f"Erreur initialisation dataset: {e}")
            self.dataset = {"anime": []}
            self._anime_dict = {}

    def _load_local_dataset(self) -> Dict[str, Any]:
        try:
            with open(self.dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            logger.warning(f"Erreur lecture dataset local: {e}")
            return {"anime": []}

    async def _download_and_save_dataset(self):
        try:
            if not settings.DATASET_URL:
                logger.warning("DATASET: DATASET_URL non configurée")
                return

            logger.log("DATASET", f"Téléchargement depuis: {settings.DATASET_URL}")
            response = await self.http_client.get(settings.DATASET_URL)
            response.raise_for_status()

            remote_dataset = safe_json_decode(response, "dataset distant", default=None)
            if not remote_dataset:
                return

            os.makedirs(os.path.dirname(self.dataset_path), exist_ok=True)

            with open(self.dataset_path, 'w', encoding='utf-8') as f:
                json.dump(remote_dataset, f, ensure_ascii=False, indent=2)

            self.dataset = remote_dataset
            logger.log("SUCCESS", f"Dataset téléchargé et sauvé - {len(self.dataset.get('anime', []))} anime")

        except Exception as e:
            logger.error(f"Erreur téléchargement dataset: {e}")
            self.dataset = {"anime": []}

    def _build_search_cache(self):
        self._anime_dict = {}

        for anime in self.dataset.get("anime", []):
            anime_slug = anime.get("slug")
            if anime_slug:
                if anime_slug not in self._anime_dict:
                    self._anime_dict[anime_slug] = {"streams": []}
                for stream in anime.get("streams", []):
                    season = stream.get("season")
                    episode = stream.get("episode")
                    language = stream.get("language")
                    urls = stream.get("urls", [])

                    if all([season is not None, episode is not None, language]):
                        for url in urls:
                            if url:
                                self._anime_dict[anime_slug]["streams"].append({
                                    "season": season,
                                    "episode": episode,
                                    "language": language,
                                    "url": url
                                })

    async def get_streams(self, anime_slug: str, season: int, episode: int, language_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            # Copier les données sous lock (opération rapide)
            async with self._dataset_lock:
                if not self.dataset.get("anime") or anime_slug not in self._anime_dict:
                    return []
                # Copie rapide des streams pour cet anime
                streams_copy = self._anime_dict[anime_slug]["streams"].copy()

            # Traiter les données HORS du lock (libère le lock plus vite)
            matching_streams = []
            for stream in streams_copy:
                if stream["season"] == season and stream["episode"] == episode:
                    if language_filter and language_filter != "Tout":
                        if language_filter == "VOSTFR" and stream["language"] != "VOSTFR":
                            continue
                        elif language_filter == "VF" and stream["language"] not in ["VF", "VF1", "VF2"]:
                            continue
                    matching_streams.append({
                        "url": stream["url"],
                        "language": stream["language"]
                    })

            if matching_streams:
                logger.debug(f"DATASET: {len(matching_streams)} streams trouvés pour {anime_slug} S{season}E{episode}")

            return matching_streams

        except Exception as e:
            logger.error(f"Erreur récupération streams dataset {anime_slug}: {e}")
            return []

    async def _periodic_update(self):
        while True:
            try:
                if settings.DATASET_UPDATE_INTERVAL <= 0:
                    logger.log("DATASET", "Mise à jour périodique désactivée (intervalle <= 0)")
                    break

                await asyncio.sleep(settings.DATASET_UPDATE_INTERVAL)

                if not settings.DATASET_URL:
                    continue

                logger.debug("🔄 DATASET: Vérification mise à jour")

                response = await self.http_client.get(settings.DATASET_URL)
                response.raise_for_status()
                remote_dataset = safe_json_decode(response, "mise à jour dataset", default=None)
                if not remote_dataset:
                    return

                with open(self.dataset_path, 'w', encoding='utf-8') as f:
                    json.dump(remote_dataset, f, ensure_ascii=False, indent=2)

                async with self._dataset_lock:
                    self.dataset = remote_dataset
                    self._build_search_cache()

                logger.log("SUCCESS", f"Dataset mis à jour - {len(self.dataset.get('anime', []))} anime")

            except Exception as e:
                logger.warning(f"Erreur mise à jour périodique dataset: {e}")


_dataset_loader: Optional[DatasetLoader] = None


# ===========================
# Récupérateur de Dataset Loader
# ===========================
def get_dataset_loader() -> Optional[DatasetLoader]:
    """
    Retourne le Dataset Loader global.
    Cette fonction n'est pas async donc pas de lock.
    Utilisée uniquement dans des contextes où le loader est déjà initialisé.
    """
    return _dataset_loader


# ===========================
# Définisseur de Dataset Loader
# ===========================
def set_dataset_loader(loader: DatasetLoader):
    global _dataset_loader
    _dataset_loader = loader
