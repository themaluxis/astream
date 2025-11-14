from abc import ABC
from typing import Any

from astream.utils.http_client import HttpClient


# ===========================
# Classe BaseScraper
# ===========================
class BaseScraper(ABC):

    def __init__(self, client: HttpClient, base_url: str):
        self.client = client
        self.base_url = base_url

    async def _internal_request(self, method: str, url: str, **kwargs) -> Any:
        return await self._execute_request(method, url, **kwargs)

    async def _execute_request(self, method: str, url: str, **kwargs) -> Any:
        method_lower = method.lower()

        if method_lower == 'get':
            return await self.client.get(url, **kwargs)
        elif method_lower == 'post':
            return await self.client.post(url, **kwargs)
        elif method_lower == 'put':
            return await self.client.put(url, **kwargs)
        elif method_lower == 'delete':
            return await self.client.delete(url, **kwargs)
        else:
            raise ValueError(f"Méthode HTTP non supportée: {method}")
