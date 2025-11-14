from typing import Any, Optional, Dict
from contextlib import asynccontextmanager
from collections import defaultdict

from astream.utils.database import (
    get_metadata_from_cache,
    set_metadata_to_cache,
    DistributedLock
)
from astream.utils.logger import logger


# ===========================
# Classe CacheKeys
# ===========================
class CacheKeys:

    @staticmethod
    def homepage() -> str:
        return "as:homepage"

    @staticmethod
    def anime_details(anime_slug: str) -> str:
        return f"as:{anime_slug}"

    @staticmethod
    def planning() -> str:
        return "as:planning"


# ===========================
# Statistiques de cache
# ===========================
class CacheStats:
    """Collecte des statistiques de cache par catégorie"""

    def __init__(self):
        self.stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"hits": 0, "misses": 0})

    def record_hit(self, category: str):
        """Enregistre un cache hit"""
        self.stats[category]["hits"] += 1

    def record_miss(self, category: str):
        """Enregistre un cache miss"""
        self.stats[category]["misses"] += 1

    def get_summary(self) -> Dict[str, Dict[str, Any]]:
        """Retourne un résumé des statistiques"""
        summary = {}
        for category, counts in self.stats.items():
            total = counts["hits"] + counts["misses"]
            hit_rate = (counts["hits"] / total * 100) if total > 0 else 0
            summary[category] = {
                "hits": counts["hits"],
                "misses": counts["misses"],
                "total": total,
                "hit_rate": hit_rate
            }
        return summary

    def log_summary(self):
        """Log le résumé des statistiques avec le level INFO"""
        summary = self.get_summary()
        if not summary:
            return

        for category, stats in summary.items():
            logger.info(
                f"{category}: {stats['hits']} hits, {stats['misses']} misses "
                f"({stats['hit_rate']:.1f}% hit rate, {stats['total']} total)"
            )

    def reset(self):
        """Réinitialise les statistiques"""
        self.stats.clear()


# Instance globale des statistiques
cache_stats = CacheStats()


# ===========================
# Gestionnaire de cache
# ===========================
class CacheManager:

    @staticmethod
    async def get(cache_key: str) -> Optional[Any]:
        cached_data = await get_metadata_from_cache(cache_key)
        if cached_data:
            return cached_data
        return None

    @staticmethod
    async def set(cache_key: str, data: Any, ttl: Optional[int] = None) -> None:
        await set_metadata_to_cache(cache_key, data, ttl)

    @staticmethod
    @asynccontextmanager
    async def with_lock(lock_key: str, instance_id: Optional[str] = None):
        async with DistributedLock(lock_key, instance_id):
            yield

    @staticmethod
    async def get_or_fetch(
        cache_key: str,
        fetch_func,
        lock_key: Optional[str] = None,
        ttl: Optional[int] = None,
        instance_id: Optional[str] = None
    ) -> Any:
        cached = await CacheManager.get(cache_key)
        if cached is not None:
            return cached

        if lock_key:
            async with CacheManager.with_lock(lock_key, instance_id):
                cached = await CacheManager.get(cache_key)
                if cached is not None:
                    return cached

                data = await fetch_func()
                if data:
                    await CacheManager.set(cache_key, data, ttl)
                return data
        else:
            data = await fetch_func()
            if data:
                await CacheManager.set(cache_key, data, ttl)
            return data
