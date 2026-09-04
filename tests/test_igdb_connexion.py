"""
Test de connexion à l'API IGDB.

Variables d'environnement attendues (token déjà généré côté Twitch) :
    IGDB_CLIENT_ID
    IGDB_ACCESS_TOKEN

Le token Twitch expire au bout de ~60 jours : s'il expire, il faudra
en régénérer un (POST https://id.twitch.tv/oauth2/token) et mettre à jour
la variable d'environnement.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ["IGDB_CLIENT_ID"]
ACCESS_TOKEN = os.environ["IGDB_ACCESS_TOKEN"]


def test_igdb_connection() -> None:
    response = requests.post(
        "https://api.igdb.com/v4/games",
        headers={
            "Client-ID": CLIENT_ID,
            "Authorization": f"Bearer {ACCESS_TOKEN}",
        },
        data="fields name, genres.name; limit 5;",
    )
    response.raise_for_status()

    games = response.json()
    print(f"Connexion IGDB OK - {len(games)} jeux récupérés :")
    for game in games:
        print(f"  - {game.get('name')}")


if __name__ == "__main__":
    test_igdb_connection()