import re
from typing import List, Optional

from astream.utils.logger import logger

PANNEAU_ANIME_PATTERN = re.compile(r'panneauAnime\("(.+?)", *"(.+?)"\);')
NEWSPF_PATTERN = re.compile(r'newSPF\("([^"]+)"\)')
SEASON_PATTERNS = [
    re.compile(r'saison\s*(\d+)(?:-(\d+))?'),
    re.compile(r'season\s*(\d+)(?:-(\d+))?'),
    re.compile(r'saga\s*(\d+)(?:-(\d+))?'),
    re.compile(r's(\d+)(?:-(\d+))?')
]

VIDEO_URL_PATTERNS = [
    re.compile(r'''['"]([^'"]*\/[^'"]*\.m3u8[^'"]*)['"]'''),
    re.compile(r'''['"]([^'"]*\/[^'"]*\.mp4[^'"]*)['"]'''),
    re.compile(r'''['"]([^'"]*\/[^'"]*\.mkv[^'"]*)['"]''')
]


# ===========================
# Extraction du slug d'anime
# ===========================
def extract_anime_slug_from_url(url: str) -> Optional[str]:
    try:
        if '/catalogue/' in url:
            if url.startswith('https://'):
                slug = url.split('/catalogue/')[-1].rstrip('/')
            else:
                slug = url.split('/catalogue/')[-1].rstrip('/') if url.startswith('/catalogue/') else url.split('/')[-1]

            parts = slug.split('/')
            return parts[0] if parts else None
        return None
    except Exception as e:
        logger.warning(f"Erreur extraction slug: {e}")
        return None


# ===========================
# Extraction d'URL vidéo
# ===========================
def extract_video_urls_from_text(text: str, source_url: str) -> List[str]:
    urls = []

    for pattern in VIDEO_URL_PATTERNS:
        matches = pattern.findall(text)
        urls.extend(matches)

    unique_urls = list(set(urls))

    source_host = ""
    if "://" in source_url:
        source_host = source_url.split("://")[1].split("/")[0]

    for url in unique_urls:
        if "://" not in url:
            continue

        found_host = url.split("://")[1].split("/")[0]

        if found_host == source_host:
            logger.debug(f"URL ignorée (même host): {url}")
            continue

        if not any(ext in url for ext in ['.m3u8', '.mp4', '.mkv']):
            continue

        # PREMIÈRE URL valide trouvée → STOP !
        logger.debug(f"PREMIÈRE URL valide trouvée - ARRÊT: {url}")
        return [url]

    logger.debug("Aucune URL vidéo valide trouvée")
    return []


# ===========================
# Nettoyage du titre
# ===========================
def clean_anime_title(title: str) -> str:
    try:
        cleaned = title.strip()

        cleaned = re.sub(r'\s+\((?:VOSTFR|VF|SUB|DUB)\)$', '', cleaned, flags=re.IGNORECASE)

        cleaned = re.sub(r'\s+', ' ', cleaned)

        return cleaned.strip()

    except Exception as e:
        logger.warning(f"Erreur nettoyage titre '{title}': {e}")
        return title


# ===========================
# Analyse des genres
# ===========================
def parse_genres_string(genres_text: str) -> List[str]:
    if not genres_text:
        return []

    genres = re.split(r'[,;/-]+', genres_text)
    return [g.strip() for g in genres if g.strip()]
