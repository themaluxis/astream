from typing import Optional
from pydantic import BaseModel, field_validator
import orjson
import base64
from astream.utils.logger import logger
from astream.config.settings import SUPPORTED_LANGUAGES, VALID_LANGUAGE_CODES


# ===========================
# Classe ConfigModel
# ===========================
class ConfigModel(BaseModel):
    language: Optional[str] = "Tout"
    languageOrder: Optional[str] = "VOSTFR,VF"
    tmdbApiKey: Optional[str] = None
    tmdbEnabled: Optional[bool] = True
    tmdbEpisodeMapping: Optional[bool] = False
    userExcludedDomains: Optional[str] = ""

    @field_validator("language")
    def check_language(cls, v):

        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Langue invalide: {SUPPORTED_LANGUAGES}")
        return v

    @field_validator("languageOrder")
    def check_language_order(cls, v):

        if not v:
            return "VOSTFR,VF"

        valid_langs = [lang for lang in VALID_LANGUAGE_CODES if lang in ["VOSTFR", "VF"]]
        langs = [lang.strip().upper() for lang in v.split(',')]

        for lang in langs:
            if lang not in valid_langs:
                return "VOSTFR,VF"

        return ','.join(langs)

    @field_validator("tmdbApiKey")
    def check_tmdb_api_key(cls, v):

        if v and len(v.strip()) < 10:
            raise ValueError("Clé API TMDB invalide")
        return v.strip() if v else None

    @field_validator("userExcludedDomains")
    def check_user_excluded_domains(cls, v):

        if not v:
            return ""

        if ' ' in v:
            raise ValueError("Espaces non autorisés dans les exclusions")

        patterns = [pattern.strip() for pattern in v.split(',') if pattern.strip()]

        valid_patterns = [p for p in patterns if p and len(p) > 0]

        return ','.join(valid_patterns)


# ===========================
# Instance de configuration par défaut
# ===========================
default_config = ConfigModel().model_dump()


# ===========================
# Validation de configuration
# ===========================
def validate_config(b64config: str) -> dict:
    try:
        try:
            decoded_config = base64.urlsafe_b64decode(b64config).decode()
        except Exception:
            raise ValueError("Chaîne base64 invalide")
        config = orjson.loads(decoded_config)
        validated_config = ConfigModel(**config).model_dump()
        return validated_config
    except (ValueError, TypeError, KeyError):
        logger.warning("Config utilisateur invalide. Retour config par défaut")
        return default_config
    except Exception:
        logger.error("Erreur validation configuration. Retour config par défaut")
        return default_config
