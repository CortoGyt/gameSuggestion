from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str

    # APIs (optionnelles : chaque script vérifie celles dont il a besoin)
    IGDB_CLIENT_ID: str | None = None
    IGDB_CLIENT_SECRET: str | None = None  # utilisé par ingest_igdb.py pour obtenir le token
    IGDB_ACCESS_TOKEN: str | None = None  # utilisé seulement par tests/test_igdb_connexion.py
    STEAM_API_KEY: str | None = None

    # Groq (labelling de secours)
    GROQ_API_KEY: str | None = None
    GROQ_LABELLING_MODEL_ID: str = "llama-3.1-8b-instant"

    # SVD
    SVD_MODEL_PATH: str = "ml/svd/modele_svd.pkl"
    SVD_DIMENSIONS: int = 50

    # Vector DB Chroma
    CHROMA_DB_PATH: str = "ml/vectorstore/chroma_db"
    CHROMA_COLLECTION: str = "games"

    # MLflow
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"

    # Authentification (JWT)
    JWT_SECRET_KEY: str
    JWT_EXPIRE_MINUTES: int = 60

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:8501"  # séparées par des virgules


# Caching des parametres
@lru_cache
def get_settings():
    return Settings()
