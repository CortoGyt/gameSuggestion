"""Reset the game data, then reload the seed list (one game name per line).

DELETES: Games, Styles, Style_Games, Textes, Users_Games, Preferences_Styles
         (the last four go by cascade from Games / Styles); AUTO_INCREMENT counters restart at 1
KEEPS:   Users, Roles, Preferences, EchellesDE, EchellesRG

Usage (from the project root):
    python -m ingestion.reset_games                          # shows what will happen, asks to confirm
    python -m ingestion.reset_games --seed data/games_seed.txt --yes
"""
import argparse

from config.settings import get_settings
from sqlalchemy import create_engine, text

COUNTED_TABLES = ["Games", "Styles", "Style_Games", "Textes", "Users_Games", "Preferences_Styles"]
RESET_ID_TABLES = ["Games", "Styles", "Textes"]


def read_seed(path: str) -> list[str]:
    names = []
    seen = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            name = line.strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return names


def count_rows(engine) -> dict[str, int]:
    counts = {}
    with engine.connect() as conn:
        for table in COUNTED_TABLES:
            counts[table] = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", default="data/games_seed.txt", help="file with one game name per line")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation question")
    args = parser.parse_args()

    names = read_seed(args.seed)  # fails here, before touching the database, if the file is missing
    if not names:
        print(f"{args.seed} is empty, nothing to load. Aborting.")
        return

    engine = create_engine(get_settings().DATABASE_URL)
    try:
        print(f"Base : {engine.url.database} sur {engine.url.host}")
        print("Sera supprimé :")
        for table, n in count_rows(engine).items():
            print(f"  {table:18} {n} lignes")
        print("Sera conservé : Users, Roles, Preferences, EchellesDE, EchellesRG")
        print(f"Sera rechargé : {len(names)} jeux depuis {args.seed}")

        if not args.yes:
            answer = input("Tape 'oui' pour confirmer : ")
            if answer.strip().lower() != "oui":
                print("Annulé, rien n'a été modifié.")
                return

        # 1) delete the data (cascade handles Style_Games, Textes, Users_Games, Preferences_Styles)
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM Games"))
            conn.execute(text("DELETE FROM Styles"))

        # 2) restart the ids at 1 (DDL: committed on its own by MySQL)
        with engine.begin() as conn:
            for table in RESET_ID_TABLES:
                conn.execute(text(f"ALTER TABLE {table} AUTO_INCREMENT = 1"))

        # 3) load the seed list
        with engine.begin() as conn:
            for name in names:
                conn.execute(
                    text("INSERT INTO Games (game_name) VALUES (:name)"),
                    {"name": name},
                )

        print(f"Terminé : {count_rows(engine)['Games']} jeux dans Games.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
