from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from config.settings import get_settings


@lru_cache
def get_engine():
    # Créé au premier appel seulement : importer l'API ne se connecte pas à MySQL
    return create_engine(get_settings().DATABASE_URL, pool_pre_ping=True)


def get_db():
    # Dépendance FastAPI : une session par requête, fermée à la fin
    with Session(get_engine()) as db:
        yield db
