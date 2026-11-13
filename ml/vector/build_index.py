"""Construit (ou met à jour) l'index ChromaDB à partir de la table Textes.

Usage (depuis la racine du projet) :
    python -m ml.vector.build_index           # ajoute / met à jour les morceaux
    python -m ml.vector.build_index --reset   # repart d'un index vide
"""
import argparse
import time

from sqlalchemy import create_engine, text

from config.settings import get_settings
from ml.vector.chromadb_vector import ChromaStore

BATCH_SIZE = 20  # nombre de textes envoyés à Chroma à la fois


def load_texts(conn):
    rows = conn.execute(
        text(
            "SELECT t.game_id, g.game_name, t.source, t.content "
            "FROM Textes t JOIN Games g ON g.id = t.game_id ORDER BY t.game_id, t.source"
        )
    ).fetchall()
    texts = []
    for row in rows:
        texts.append(
            {"game_id": row.game_id, "game_name": row.game_name, "source": row.source, "content": row.content}
        )
    return texts


def main():
    parser = argparse.ArgumentParser(description="Index ChromaDB des textes de jeux")
    parser.add_argument("--reset", action="store_true", help="Vide l'index avant de le reconstruire")
    args = parser.parse_args()

    engine = create_engine(get_settings().DATABASE_URL)
    with engine.connect() as conn:
        texts = load_texts(conn)
    print(str(len(texts)) + " texte(s) à indexer")

    store = ChromaStore()
    if args.reset:
        store.reset()

    start = time.time()
    total_chunks = 0
    for position in range(0, len(texts), BATCH_SIZE):
        total_chunks += store.upsert_texts(texts[position : position + BATCH_SIZE])
        print("  " + str(min(position + BATCH_SIZE, len(texts))) + "/" + str(len(texts)))

    seconds = round(time.time() - start, 1)
    print(str(total_chunks) + " morceaux envoyés en " + str(seconds) + " s ; " + str(store.count()) + " dans l'index")


if __name__ == "__main__":
    main()