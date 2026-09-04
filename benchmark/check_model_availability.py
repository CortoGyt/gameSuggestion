import time

import requests
from config.settings import get_settings
from huggingface_hub import InferenceClient


def classify_error(exception):
    """
    Classifie une exception en catégorie d'erreur selon le code HTTP numérique.
    Retombe sur l'analyse du texte si le code HTTP n'est pas accessible.
    """
    # Essaie de lire le code HTTP de la réponse
    try:
        status_code = exception.response.status_code

        # Classification par code HTTP numérique
        if status_code == 403:
            return "gated"
        elif status_code == 404:
            return "introuvable"
        elif status_code == 503:
            return "en chargement"
        elif status_code == 429:
            return "quota dépassé"
        else:
            return "erreur"

    except AttributeError:
        # Pas d'attribut response/status_code : analyse le texte du message
        error_str = str(exception).lower()

        # Erreur 403: Accès refusé (modèle gated, authentification insuffisante)
        if "403" in error_str or "forbidden" in error_str or "access denied" in error_str:
            return "gated"

        # Erreur 404: Modèle introuvable
        if "404" in error_str or "not found" in error_str:
            return "introuvable"

        # Erreur 503: Service indisponible (modèle en cours de chargement)
        if "503" in error_str or "service unavailable" in error_str or "model is loading" in error_str:
            return "en chargement"

        # Erreur 429: Trop de requêtes (quota dépassé, limite de débit)
        if "429" in error_str or "rate limit" in error_str or "quota" in error_str:
            return "quota dépassé"

        # Tout autre cas d'erreur
        return "erreur"


def fetch_available_models():
    """
    Découvre les modèles text-generation depuis 6 auteurs différents via l'API Hugging Face Hub.
    Retourne une liste de noms de modèles uniques (jusqu'à 12 modèles) ou None si aucun modèle trouvé.
    """
    url = "https://huggingface.co/api/models"

    # Liste des auteurs pour la diversité
    authors = ["meta-llama", "Qwen", "mistralai", "google", "deepseek-ai", "microsoft"]

    all_models = []
    model_ids_seen = set()

    # Boucle sur chaque auteur
    for author in authors:
        params = {
            "inference_provider": "all",
            "pipeline_tag": "text-generation",
            "author": author,
            "sort": "trendingScore",
            "limit": 2
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            models_data = response.json()

            # Extrait les noms de modèles
            for m in models_data:
                if isinstance(m, dict) and "id" in m:
                    model_id = m["id"]
                    # Ajoute seulement si ce n'est pas un doublon
                    if model_id not in model_ids_seen:
                        all_models.append(model_id)
                        model_ids_seen.add(model_id)

        except requests.exceptions.RequestException as e:
            # Log l'erreur et continue avec l'auteur suivant
            print(f"Avertissement: impossible de récupérer les modèles de {author}: {e}")
            continue

    # Retourne None si aucun modèle n'a pu être récupéré
    if len(all_models) == 0:
        return None

    return all_models


def check_models():
    """
    Découvre les modèles trending et teste leur disponibilité via InferenceClient.
    Affiche un tableau récapitulatif avec nom, statut, et temps de réponse.
    """
    print("Récupération des modèles trending depuis Hugging Face Hub...")
    models = fetch_available_models()

    if models is None:
        print("Erreur : Impossible de récupérer la liste des modèles depuis l'API Hub.")
        print("Vérifiez votre connexion réseau et réessayez.")
        return

    if not models:
        print("Aucun modèle trouvé avec les critères spécifiés.")
        return

    print(f"{len(models)} modèles découverts\n")
    print("Test de disponibilité...")
    print()

    results = []

    for model in models:
        status = "erreur"
        response_time = None

        try:
            client = InferenceClient(token=get_settings().HF_TOKEN, provider="auto")
            start = time.time()
            response = client.chat_completion(
                model=model,
                messages=[{"role": "user", "content": "Réponds juste OK"}],
                max_tokens=5
            )
            response_time = time.time() - start
            status = "disponible"
        except Exception as e:
            status = classify_error(e)

        results.append({
            "modèle": model,
            "statut": status,
            "temps (s)": f"{response_time:.2f}" if response_time is not None else ""
        })

    # Affiche le tableau récapitulatif
    print("\n" + "=" * 80)
    print(f"{'Modèle':<45} {'Statut':<20} {'Temps (s)':<10}")
    print("=" * 80)
    for result in results:
        print(f"{result['modèle']:<45} {result['statut']:<20} {result['temps (s)']:<10}")
    print("=" * 80)

    # Résumé
    available_count = 0
    for r in results:
        if r["statut"] == "disponible":
            available_count += 1
    print(f"\nRésumé: {available_count}/{len(results)} modèle(s) disponible(s)")


if __name__ == "__main__":
    check_models()
