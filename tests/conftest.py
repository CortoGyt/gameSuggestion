import os

# Doit être défini avant l'import de main (qui lit les settings)
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "cle-de-test-seulement-0123456789abcdef")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api.database import get_db
from main import app

# Mini base de test : seulement les tables et colonnes que l'API lit
TABLES = [
    "CREATE TABLE EchellesDE (id INTEGER PRIMARY KEY, label TEXT)",
    "CREATE TABLE EchellesRG (id INTEGER PRIMARY KEY, label TEXT)",
    "CREATE TABLE Games (id INTEGER PRIMARY KEY, game_name TEXT, game_length INT,"
    " game_dimension TEXT, difficulty_id INT, execution_id INT, randomness_id INT,"
    " glitchness_id INT)",
    "CREATE TABLE Styles (id INTEGER PRIMARY KEY, style_name TEXT)",
    "CREATE TABLE Style_Games (game_id INT, style_id INT)",
    "CREATE TABLE Roles (id INTEGER PRIMARY KEY, name TEXT)",
    "CREATE TABLE Users (id INTEGER PRIMARY KEY, user_name TEXT UNIQUE, user_pw_hash TEXT, role_id INT)",
]

# Trois jeux : Celeste, Peggle, Hades
DONNEES = [
    "INSERT INTO EchellesDE VALUES (1, 'Facile'), (3, 'Avancé')",
    "INSERT INTO EchellesRG VALUES (1, 'Aucun'), (2, 'Bas')",
    "INSERT INTO Games VALUES (1, 'Celeste', 25, '2D', 3, 3, 1, 2),"
    " (2, 'Peggle', 60, '2D', 1, 1, 1, 1), (3, 'Hades', 90, '3D', 3, 3, 2, 1)",
    "INSERT INTO Styles VALUES (1, 'Platformer'), (2, 'Puzzle'), (3, 'Roguelike')",
    "INSERT INTO Style_Games VALUES (1, 1), (2, 2), (3, 3), (3, 1)",
    "INSERT INTO Roles VALUES (1, 'user'), (2, 'admin')",
]


@pytest.fixture
def client():
    # Base sqlite en mémoire, recréée pour chaque test : pas besoin de MySQL
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        for requete in TABLES + DONNEES:
            connection.execute(text(requete))

    def fausse_base():
        with Session(engine) as db:
            yield db

    # L'API utilise la fausse base au lieu de MySQL
    app.dependency_overrides[get_db] = fausse_base
    yield TestClient(app)
    app.dependency_overrides.clear()
