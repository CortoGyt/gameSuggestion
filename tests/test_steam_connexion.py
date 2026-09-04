"""
Test de connexion à l'API publique Steam (appdetails + reviews).

Ces deux endpoints ne nécessitent pas STEAM_API_KEY (ils sont publics),
mais l'API n'est pas officiellement documentée/garantie stable.
STEAM_API_KEY ne sera utile que si tu ajoutes plus tard un appel à l'API
Steam Web officielle (ex: liste des jeux, stats joueurs).

Le blurb (description courte) vient d'appdetails, les tags/reviews de l'endpoint appreviews.
"""
import requests

APPID_TEST = 367520  # Hollow Knight, à titre d'exemple


def test_steam_connection() -> None:
    details = requests.get(
        "https://store.steampowered.com/api/appdetails",
        params={"appids": APPID_TEST},
    )
    details.raise_for_status()
    data = details.json()[str(APPID_TEST)]["data"]
    print("Connexion Steam (appdetails) OK :")
    print(f"  - Nom : {data.get('name')}")
    print(f"  - Blurb : {data.get('short_description')[:120]}...")

    reviews = requests.get(
        f"https://store.steampowered.com/appreviews/{APPID_TEST}",
        params={"json": 1, "num_per_page": 3},
    )
    reviews.raise_for_status()
    review_data = reviews.json()
    print(f"\nConnexion Steam (reviews) OK - {review_data['query_summary']['total_reviews']} avis au total")


if __name__ == "__main__":
    test_steam_connection()
