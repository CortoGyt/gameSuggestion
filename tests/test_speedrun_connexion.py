"""
Test de connexion à l'API publique speedrun.com (v1).
Aucune clé nécessaire. Doc : https://github.com/speedruncomorg/api
"""
import requests

GAME_NAME_TEST = "Celeste"


def test_speedrun_connection() -> None:
    response = requests.get(
        "https://www.speedrun.com/api/v1/games",
        params={"name": GAME_NAME_TEST, "max": 1},
    )
    response.raise_for_status()
    games = response.json()["data"]
    print(f"Connexion speedrun.com OK - {len(games)} résultat(s) pour '{GAME_NAME_TEST}' :")
    for game in games:
        print(f"  - {game['names']['international']} (id: {game['id']})")


if __name__ == "__main__":
    test_speedrun_connection()