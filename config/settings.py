from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    # APIs
    IGDB_CLIENT_ID: str
    IGDB_ACCESS_TOKEN: str
    STEAM_API_KEY: str

    # LLM  HuggingFace
    HF_LABELLING_MODEL_ID: str = "Qwen/Qwen3-4B-Instruct-2507" #labellise le jeux à l'initial après récup via api speedrun.com
    HF_MODEL_ID: str = "meta-llama/Llama-2-7b-chat-hf"  # placeholder, à check plus tard
    HF_TOKEN: str | None = None  # Token HuggingFace si modèle gated

    # SVD
    SVD_MODEL_PATH: str = "ml/svd/models/svd_model.pkl"
    SVD_DIMENSIONS: int = 50

    # Vector DB Chroma
    CHROMA_DB_PATH: str = "ml/vectorstore/chroma_db"
    CHROMA_COLLECTION: str = "games"

    # Embedding Model
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # MLflow
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    class Config:
        env_file = ".env"
        extra="ignore"


# Caching des parametres
@lru_cache
def get_settings():
    return Settings()
