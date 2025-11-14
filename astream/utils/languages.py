from typing import List, Optional, Dict, Any


# ===========================
# Filtrage de langue
# ===========================
def normalize_language(language: str) -> str:
    if language.upper() in ["VF1", "VF2"]:
        return "VF"
    return language.upper()


def filter_by_language(items: List[Dict[str, Any]], language_filter: Optional[str], language_key: str = "language") -> List[Dict[str, Any]]:
    if not language_filter or language_filter == "Tout":
        return items

    normalized_filter = normalize_language(language_filter)

    filtered = []
    for item in items:
        item_language = item.get(language_key, "")
        if normalize_language(item_language) == normalized_filter:
            filtered.append(item)

    return filtered


def sort_by_language_priority(items: List[Dict[str, Any]], language_order: Optional[str], language_key: str = "language") -> List[Dict[str, Any]]:
    if not language_order:
        return items

    priority_list = [lang.strip().upper() for lang in language_order.split(",")]

    def get_priority(item):
        item_language = normalize_language(item.get(language_key, ""))

        for idx, priority_lang in enumerate(priority_list):
            if item_language == normalize_language(priority_lang):
                return idx

        return len(priority_list)

    return sorted(items, key=get_priority)
