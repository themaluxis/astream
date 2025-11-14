from typing import List
from astream.utils.logger import logger
from astream.config.settings import settings, DEFAULT_EXCLUDED_DOMAINS


# ===========================
# Aides d'exclusion de domaines
# ===========================
def get_all_excluded_domains() -> str:
    all_excluded = DEFAULT_EXCLUDED_DOMAINS.copy()

    if settings.EXCLUDED_DOMAINS:
        user_domains = [d.strip() for d in settings.EXCLUDED_DOMAINS.split(',') if d.strip()]
        all_excluded.extend(user_domains)

    seen = set()
    unique_excluded = []
    for domain in all_excluded:
        if domain.lower() not in seen:
            seen.add(domain.lower())
            unique_excluded.append(domain)

    return ",".join(unique_excluded)


# ===========================
# Filtrage de domaines
# ===========================
def filter_excluded_domains(urls: List[str], user_excluded_domains: str = "") -> List[str]:
    try:
        all_exclusions = DEFAULT_EXCLUDED_DOMAINS.copy()

        server_excluded = getattr(settings, 'EXCLUDED_DOMAINS', '')
        server_domains = []
        if server_excluded:
            server_domains = [domain.strip() for domain in server_excluded.split(',') if domain.strip()]
            all_exclusions.extend(server_domains)

        if user_excluded_domains:
            all_exclusions.extend([domain.strip() for domain in user_excluded_domains.split(',') if domain.strip()])

        if not all_exclusions:
            return urls

        seen = set()
        unique_exclusions = []
        for exclusion in all_exclusions:
            if exclusion.lower() not in seen:
                seen.add(exclusion.lower())
                unique_exclusions.append(exclusion)

        filtered_urls = []
        excluded_counts = {"défaut": 0, "serveur": 0, "utilisateur": 0}

        for url in urls:
            excluded = False
            excluded_by = None

            for pattern in unique_exclusions:
                if pattern in url:
                    excluded = True
                    excluded_by = pattern
                    break

            if excluded:
                if excluded_by in DEFAULT_EXCLUDED_DOMAINS:
                    excluded_counts["défaut"] += 1
                elif excluded_by in server_domains:
                    excluded_counts["serveur"] += 1
                else:
                    excluded_counts["utilisateur"] += 1
            else:
                filtered_urls.append(url)

        total_filtered = len(urls) - len(filtered_urls)
        if total_filtered > 0:
            sources_str = ", ".join(f"{src}: {count}" for src, count in excluded_counts.items() if count > 0)
            logger.debug(f"EXCLUDED {total_filtered}/{len(urls)} URLs ({sources_str})")

        return filtered_urls

    except Exception as e:
        logger.warning(f"Erreur filtrage exclusions: {e}")
        return urls
