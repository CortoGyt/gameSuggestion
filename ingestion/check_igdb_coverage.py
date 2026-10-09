"""Coverage check after the IGDB enrichment (read-only).

Usage (from the project root):
    python -m ingestion.check_igdb_coverage                  # totals + first 15 games
    python -m ingestion.check_igdb_coverage --all            # totals + every game
    python -m ingestion.check_igdb_coverage --name celeste   # totals + games whose name contains "celeste"
"""
import argparse

from config.settings import get_settings
from sqlalchemy import create_engine, text

STATS_SQL = (
    "SELECT COUNT(*), "
    "SUM(game_length IS NOT NULL), "
    "SUM(game_dimension IS NOT NULL), "
    "SUM(EXISTS (SELECT 1 FROM Style_Games sg WHERE sg.game_id = Games.id)) "
    "FROM Games"
)

LIST_SQL = (
    "SELECT g.game_name, g.game_length, g.game_dimension, "
    "GROUP_CONCAT(s.style_name SEPARATOR ', ') AS styles "
    "FROM Games g "
    "LEFT JOIN Style_Games sg ON sg.game_id = g.id "
    "LEFT JOIN Styles s ON s.id = sg.style_id "
    "{where} GROUP BY g.id ORDER BY g.id {limit}"
)


def percent(part: int, total: int) -> str:
    if total == 0:
        return "0%"
    return f"{round(100 * part / total)}%"


def format_length(minutes) -> str:
    if minutes is None:
        return "-"
    return f"{minutes} min (~{round(minutes / 60, 1)} h)"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="list every game")
    parser.add_argument("--name", default=None, help="list games whose name contains this text")
    args = parser.parse_args()

    where = ""
    limit = "LIMIT 15"
    params = {}
    if args.name:
        where = "WHERE g.game_name LIKE :pattern"
        limit = ""
        params = {"pattern": f"%{args.name}%"}
    elif args.all:
        limit = ""

    engine = create_engine(get_settings().DATABASE_URL)
    try:
        with engine.connect() as conn:
            row = conn.execute(text(STATS_SQL)).fetchone()
            total = int(row[0] or 0)
            with_length = int(row[1] or 0)
            with_dimension = int(row[2] or 0)
            with_styles = int(row[3] or 0)

            print(f"Games total        : {total}")
            print(f"avec styles (IGDB) : {with_styles} ({percent(with_styles, total)})")
            print(f"avec durée         : {with_length} ({percent(with_length, total)})")
            print(f"avec dimension     : {with_dimension} ({percent(with_dimension, total)})")

            print("\nJeux (nom | durée | dimension | styles) :")
            sql = LIST_SQL.format(where=where, limit=limit)
            for r in conn.execute(text(sql), params).fetchall():
                dimension = r[2]
                if dimension is None:
                    dimension = "-"
                print(f"- {r[0].strip()} | {format_length(r[1])} | {dimension} | {r[3]}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
