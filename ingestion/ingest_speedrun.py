import json
import os
import time

import requests
from config.settings import get_settings
from sqlalchemy import create_engine, text


def ingest_speedrun_games():
    """
    Pagine sur l'API speedrun.com pour récupérer 1000 jeux,
    les stocke dans la table Games, récupère les catégories pour chaque jeu,
    et sauvegarde les résultats dans data/speedrun_raw.json.
    """
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)

    # URL de base API
    base_url = "https://www.speedrun.com/api/v1/games"
    games_data = []
    game_count = 0
    offset = 0
    max_per_page = 200
    target_count = 1000

    print(f"Démarrage de l'ingestion depuis {base_url}...")

    try:
        # Boucle de pagination
        while game_count < target_count:
            params = {"max": max_per_page, "offset": offset}

            try:
                response = requests.get(base_url, params=params, timeout=10)
                response.raise_for_status()
            except Exception as e:
                print(f"Erreur lors de la récupération des jeux à l'offset {offset}: {e}")
                break

            data = response.json()
            games = data.get("data", [])

            if not games:
                print(f"Aucun jeu supplémentaire retourné à l'offset {offset}. Total récupéré: {game_count}")
                break

            for game in games:
                if game_count >= target_count:
                    break

                game_name = game.get("names", {}).get("international", "Inconnu")
                game_id = game.get("id")

                # Insère dans la table Games si n'existe pas
                try:
                    with engine.connect() as conn:
                        # Vérifie si le jeu existe déjà
                        result = conn.execute(
                            text("SELECT id FROM Games WHERE game_name = :name"),
                            {"name": game_name}
                        )
                        existing = result.fetchone()

                        if not existing:
                            conn.execute(
                                text("INSERT INTO Games (game_name) VALUES (:name)"),
                                {"name": game_name}
                            )
                            conn.commit()
                            print(f"Jeu inséré: {game_name}")
                        else:
                            print(f"Jeu existe déjà: {game_name}")
                except Exception as e:
                    print(f"Erreur lors de l'insertion du jeu {game_name}: {e}")

                # Récupère les catégories pour ce jeu
                categories = []
                try:
                    time.sleep(0.6)  # Limitation de débit
                    categories_url = f"{base_url}/{game_id}/categories"
                    cat_response = requests.get(categories_url, timeout=10)
                    cat_response.raise_for_status()
                    cat_data = cat_response.json()
                    categories = []
                    for cat in cat_data.get("data", []):
                        categories.append(cat.get("name", "Inconnu"))
                    print(f"{len(categories)} catégories récupérées pour {game_name}")
                except Exception as e:
                    print(f"Erreur lors de la récupération des catégories pour {game_id}: {e}")

                # Store in result
                games_data.append({
                    "game_name": game_name,
                    "categories": categories
                })

                game_count += 1

            offset += max_per_page

        # Sauvegarde dans un fichier JSON
        os.makedirs("data", exist_ok=True)
        output_path = "data/speedrun_raw.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(games_data, f, ensure_ascii=False, indent=2)

        print("\nIngestion terminée!")
        print(f"Total de jeux insérés: {game_count}")
        print(f"Résultats sauvegardés dans {output_path}")

        # Vérifie la base de données
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) as count FROM Games"))
                count = result.fetchone()[0]
                print(f"La table Games contient maintenant: {count} lignes")
        except Exception as e:
            print(f"Erreur lors de la vérification du décompte de la base de données: {e}")

    finally:
        engine.dispose()


if __name__ == "__main__":
    ingest_speedrun_games()
