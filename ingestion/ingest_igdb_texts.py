"""Ajoute un résumé IGDB dans Textes pour les jeux qui n'ont pas de texte Steam.

Utilise la recherche de ingest_igdb.py (nom exact, puis retrait d'un tag de plateforme).
Seules les correspondances "exact" et "platform" sont écrites ; "fuzzy" et "not_found" sont ignorées.
Un jeu qui a déjà un steam_blurb ou un igdb_summary est sauté : le script est relançable.

Prérequis (une fois) : db/migrations/001_add_igdb_summary.sql

Usage (depuis la racine du projet) :
    python -m ingestion.ingest_igdb_texts --limit 5
    python -m ingestion.ingest_igdb_texts
"""
import argparse

from sqlalchemy import create_engine, text

from config.settings import get_settings
from ingestion import ingest_igdb

# Demande aussi le résumé et l'histoire à IGDB (la recherche de ingest_igdb lit ce champ)
ingest_igdb.FIELDS = ingest_igdb.FIELDS + ",summary,storyline"

TRUSTED_STATUSES = ["exact", "platform"]


def build_igdb_text(game):
    # Résumé + histoire, séparés par une ligne vide ; "" si IGDB n'a rien
    parts = []
    for key in ["summary", "storyline"]:
        value = " ".join((game.get(key) or "").split())
        if value:
            parts.append(value)
    return "\n\n".join(parts)


def games_without_text(conn, limit):
    query = """
        SELECT g.id, g.game_name FROM Games g
        WHERE NOT EXISTS (
            SELECT 1 FROM Textes t
            WHERE t.game_id = g.id AND t.source IN ('steam_blurb', 'igdb_summary')
        )
        ORDER BY g.game_name
    """
    rows = conn.execute(text(query)).fetchall()
    if limit:
        rows = rows[:limit]
    return rows


def main():
    parser = argparse.ArgumentParser(description="Résumés IGDB pour les jeux sans texte Steam")
    parser.add_argument("--limit", type=int, default=0, help="Nombre maximum de jeux (0 = tous)")
    args = parser.parse_args()

    engine = create_engine(get_settings().DATABASE_URL)
    with engine.begin() as conn:
        games = games_without_text(conn, args.limit)
    print(str(len(games)) + " jeu(x) sans texte")
    if len(games) == 0:
        return

    token = ingest_igdb.get_token()
    counts = {}
    for game in games:
        name = game.game_name.strip()
        try:
            status, found = ingest_igdb.find_game(token, name)
        except Exception as exc:  # erreur réseau/API : on passe, repris au prochain lancement
            print("  [erreur] " + name + " : " + str(exc))
            continue

        content = ""
        if status in TRUSTED_STATUSES and found is not None:
            content = build_igdb_text(found)

        if content:
            with engine.begin() as conn:
                conn.execute(
                    text("INSERT INTO Textes (game_id, source, content) VALUES (:g, 'igdb_summary', :c)"),
                    {"g": game.id, "c": content},
                )
            result = "ajouté"
        elif status in TRUSTED_STATUSES:
            result = "pas de résumé"
        else:
            result = status
        counts[result] = counts.get(result, 0) + 1
        print("  " + name + " -> " + result)

    print("Bilan :", counts)
    engine.dispose()


if __name__ == "__main__":
    main()