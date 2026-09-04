"""
Crée la base de données et toutes les tables à partir de schema.sql.
Se connecte sans base sélectionnée (le CREATE DATABASE / USE de schema_db.sql s'en charge).
"""
from pathlib import Path

import pymysql
from config.settings import get_settings
from sqlalchemy.engine.url import make_url

SCHEMA_PATH = Path(__file__).parent / "schema_db.sql"


def create_database() -> None:
    url = make_url(get_settings().DATABASE_URL)

    connection = pymysql.connect(
        host=url.host,
        port=url.port or 3306,
        user=url.username,
        password=url.password,
    )
    try:
        with connection.cursor() as cursor:
            sql = SCHEMA_PATH.read_text(encoding="utf-8")
            for statement in sql.split(";"):
                statement = statement.strip()
                if statement:
                    cursor.execute(statement)
        connection.commit()
        print("Base de données créée avec succès.")
    finally:
        connection.close()


if __name__ == "__main__":
    create_database()
