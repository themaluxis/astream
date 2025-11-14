from typing import Dict, Optional, Any
from bs4 import Tag
from astream.scrapers.animesama.helpers import extract_anime_slug_from_url, clean_anime_title


# ===========================
# Classe CardParser
# ===========================
class CardParser:
    """
    Parser pour les cartes anime de la homepage Anime-Sama.

    Structure HTML (2025):
    <div class="shrink-0 catalog-card card-base">
      <a href="/catalogue/slug">
        <h2 class="card-title">Titre</h2>
        <div class="info-row">
          <span class="info-label">Genres|Types|Langues</span>
          <p class="info-value">Valeur</p>
        </div>
        <div class="synopsis-content">Synopsis...</div>
      </a>
    </div>
    """

    @staticmethod
    def _extract_poster_url(card: Tag) -> str:
        """Extrait l'URL du poster depuis une carte."""
        img = card.find('img', class_='card-image')
        if not img:
            img = card.find('img')  # Fallback sans classe
        return img.get('src', '') if img else ''

    @staticmethod
    def _extract_info_value(card: Tag, label_text: str) -> str:
        for info_row in card.find_all('div', class_='info-row'):
            label = info_row.find('span', class_='info-label')
            if label and label_text.lower() in label.get_text().lower():
                value_elem = info_row.find('p', class_='info-value')
                if value_elem:
                    return value_elem.get_text(strip=True)
        return ''

    @staticmethod
    def parse_common_fields(card: Tag) -> Dict[str, Any]:
        data = {}

        title_elem = card.find('h2', class_='card-title')
        if not title_elem:
            title_elem = card.find(['h1', 'h2', 'h3', 'h4'])  # Fallback
        if title_elem:
            raw_title = title_elem.get_text(strip=True)
            data["title"] = clean_anime_title(raw_title)

        card_url = card.get('href', '')
        if card_url:
            slug = extract_anime_slug_from_url(card_url)
            if slug:
                data["slug"] = slug

        poster_url = CardParser._extract_poster_url(card)
        if poster_url:
            data["image"] = poster_url

        languages = CardParser._extract_info_value(card, "Langues")
        if languages:
            data["languages"] = languages

        genres = CardParser._extract_info_value(card, "Genres")
        if genres:
            data["genres"] = genres

        return data

    @staticmethod
    def parse_anime_card(card: Tag) -> Optional[Dict[str, Any]]:
        data = CardParser.parse_common_fields(card)

        content_type = CardParser._extract_info_value(card, "Types")
        if content_type:
            data["type"] = content_type

        return data if data.get("slug") else None

    @staticmethod
    def parse_pepites_card(card: Tag) -> Optional[Dict[str, Any]]:
        data = CardParser.parse_common_fields(card)

        content_type = CardParser._extract_info_value(card, "Types")
        if content_type:
            data["type"] = content_type

        synopsis_elem = card.find('div', class_='synopsis-content')
        if synopsis_elem:
            synopsis_text = synopsis_elem.get_text(strip=True)
            if synopsis_text and synopsis_text != "Synopsis bientôt disponible":
                data["synopsis"] = synopsis_text

        return data if data.get("slug") else None
