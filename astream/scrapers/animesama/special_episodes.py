import re
from typing import List, Dict, Any, Set
from astream.utils.logger import logger


# ===========================
# Classe SpecialEpisodesDetector
# ===========================
class SpecialEpisodesDetector:

    def __init__(self):
        self.creer_liste_pattern = re.compile(r'creerListe\(\s*(\d+),\s*(\d+)\s*\)')
        self.newspf_pattern = re.compile(r'newSPF?\("([^"]+)"\)')
        self.finir_liste_pattern = re.compile(r'finirListe(?:OP)?\(\s*(\d+)\s*\)')

    def analyze_javascript_structure(self, html: str) -> Dict[str, Any]:
        try:
            creer_liste_calls = self.creer_liste_pattern.findall(html)
            newspf_calls = self.newspf_pattern.findall(html)
            finir_liste_calls = self.finir_liste_pattern.findall(html)

            logger.debug(f"creerListe calls trouvés: {creer_liste_calls}")
            logger.debug(f"newSPF calls trouvés: {newspf_calls}")
            logger.debug(f"finirListeOP calls trouvés: {finir_liste_calls}")

            if not creer_liste_calls or not newspf_calls:
                return {"special_episodes": [], "indices": set()}

            special_indices = self._calculate_special_indices(
                creer_liste_calls, newspf_calls, finir_liste_calls
            )

            return {
                "special_episodes": newspf_calls,
                "indices": special_indices,
                "creer_liste_calls": creer_liste_calls,
                "total_normal_episodes": self._count_normal_episodes(creer_liste_calls, finir_liste_calls)
            }

        except Exception as e:
            logger.error(f"Erreur analyse structure JavaScript: {e}")
            return {"special_episodes": [], "indices": set()}

    def _calculate_special_indices(
        self,
        creer_liste_calls: List[tuple],
        newspf_calls: List[str],
        finir_liste_calls: List[str]
    ) -> Set[int]:
        indices = set()
        current_index = 0

        for i, (debut_str, fin_str) in enumerate(creer_liste_calls):
            debut = int(debut_str)
            fin = int(fin_str)

            episodes_count = fin - debut + 1
            current_index += episodes_count

            if i < len(newspf_calls):
                indices.add(current_index)
                logger.debug(f"Épisode spécial '{newspf_calls[i]}' à l'indice {current_index}")
                current_index += 1

        return indices

    def _count_normal_episodes(
        self,
        creer_liste_calls: List[tuple],
        finir_liste_calls: List[str]
    ) -> int:

        total = 0

        for debut_str, fin_str in creer_liste_calls:
            debut = int(debut_str)
            fin = int(fin_str)
            total += fin - debut + 1

        if finir_liste_calls and creer_liste_calls:
            last_episode = int(finir_liste_calls[0])
            last_creer_liste_end = int(creer_liste_calls[-1][1])

            if last_episode > last_creer_liste_end:
                total += last_episode - last_creer_liste_end

        return total

    def filter_special_episodes(
        self,
        episodes_urls: List[str],
        html: str
    ) -> Dict[str, Any]:
        analysis = self.analyze_javascript_structure(html)
        special_indices = analysis["indices"]
        special_episodes = analysis["special_episodes"]

        if not special_indices:
            logger.debug("Aucun épisode spécial détecté")
            return {
                "filtered_urls": episodes_urls,
                "removed_specials": [],
                "original_count": len(episodes_urls),
                "filtered_count": len(episodes_urls)
            }
        filtered_urls = []
        removed_specials = []

        for i, url in enumerate(episodes_urls):
            if i in special_indices:
                special_index = len(removed_specials)
                if special_index < len(special_episodes):
                    special_name = special_episodes[special_index]
                else:
                    special_name = f"SP {special_index + 1}"

                removed_specials.append({
                    "index": i,
                    "name": special_name,
                    "url": url
                })
                logger.debug(f"Épisode spécial filtré à l'indice {i}: {special_name}")
            else:
                filtered_urls.append(url)

        logger.log("ANIMESAMA", f"Filtrage terminé: {len(episodes_urls)} → {len(filtered_urls)} épisodes (-{len(removed_specials)} SP)")

        return {
            "filtered_urls": filtered_urls,
            "removed_specials": removed_specials,
            "original_count": len(episodes_urls),
            "filtered_count": len(filtered_urls),
            "analysis": analysis
        }


# ===========================
# Instance Singleton
# ===========================
special_episodes_detector = SpecialEpisodesDetector()
