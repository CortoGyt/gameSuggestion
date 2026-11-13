"""Client minimal pour Ollama (modèle local). Un seul appel : generer(prompt)."""
import requests

from config.settings import get_settings

DELAI_MAX_SECONDES = 120  # le premier appel charge le modèle en mémoire


class LlmIndisponible(Exception):
    pass


def generer(prompt):
    settings = get_settings()
    corps = {
        "model": settings.OLLAMA_EXPLANATION_MODEL_ID,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 300},
    }
    try:
        reponse = requests.post(settings.OLLAMA_URL + "/api/chat", json=corps, timeout=DELAI_MAX_SECONDES)
        reponse.raise_for_status()
        return reponse.json()["message"]["content"].strip()
    except (requests.RequestException, KeyError, ValueError):
        raise LlmIndisponible("Appel à Ollama impossible (Ollama lancé ? modèle téléchargé ?)") from None
