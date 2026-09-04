from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    # APIs
    IGDB_CLIENT_ID: str
    IGDB_ACCESS_TOKEN: str
    STEAM_API_KEY: str
    RAWG_API_KEY: str

    # LLM - HuggingFace
    HF_MODEL_ID: str = "meta-llama/Llama-2-7b-chat-hf"  # ou autre
    HF_TOKEN: str  # Token HuggingFace si modèle gated

    # SVD
    SVD_MODEL_PATH: str = "ml/svd/models/svd_model.pkl"
    SVD_DIMENSIONS: int = 50

    # Vector DB - Chroma
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

# Caching des parametres
@lru_cache
def get_settings():
    return Settings()
