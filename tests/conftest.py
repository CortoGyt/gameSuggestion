import os

# Doit être défini avant l'import de main (qui lit les settings)
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api.database import get_db
from main import app

SCHEMA = [
    "CREATE TABLE EchellesDE (id INTEGER PRIMARY KEY, label TEXT)",
    "CREATE TABLE EchellesRG (id INTEGER PRIMARY KEY, label TEXT)",
    "CREATE TABLE Games (id INTEGER PRIMARY KEY, game_name TEXT, game_length INT,"
    " game_dimension TEXT, difficulty_id INT, execution_id INT, randomness_id INT,"
    " glitchness_id INT)",
    "CREATE TABLE Styles (id INTEGER PRIMARY KEY, style_name TEXT)",
    "CREATE TABLE Style_Games (game_id INT, style_id INT)",
]

DATA = [
    "INSERT INTO EchellesDE VALUES (1, 'Facile'), (3, 'Avancé')",
    "INSERT INTO EchellesRG VALUES (1, 'Aucun'), (2, 'Bas')",
    "INSERT INTO Games VALUES (1, 'Celeste', 25, '2D', 3, 3, 1, 2),"
    " (2, 'Peggle', 60, '2D', 1, 1, 1, 1), (3, 'Hades', 90, '3D', 3, 3, 2, 1)",
    "INSERT INTO Styles VALUES (1, 'Platformer'), (2, 'Puzzle'), (3, 'Roguelike')",
    "INSERT INTO Style_Games VALUES (1, 1), (2, 2), (3, 3), (3, 1)",
]


@pytest.fixture
def client():
    # Base sqlite en mémoire, recréée pour chaque test : aucun MySQL requis
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        for statement in SCHEMA:
            connection.execute(text(statement))
        for statement in DATA:
            connection.execute(text(statement))

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
