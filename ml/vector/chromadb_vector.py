import chromadb
from chromadb.config import Settings as ChromaSettings
from config.settings import get_settings
from sentence_transformers import SentenceTransformer


class ChromaStore:
    def __init__(self):
        self.settings = get_settings()
        self.client = chromadb.Client(
            ChromaSettings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=self.settings.CHROMA_DB_PATH,
                anonymized_telemetry=False
            )
        )
        self.embedding_model = SentenceTransformer(
            self.settings.EMBEDDING_MODEL
        )
        self.collection = self.client.get_or_create_collection(
            name=self.settings.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"}
        )

    def add_games(self, games: list[dict]):
        """Ajouter des jeux à Chroma
        games: [{"id": str, "name": str, "description": str, "metadata": dict}, ...]
        """
        documents = []
        metadatas = []
        ids = []
        names = []
        for g in games:
            documents.append(g["description"])
            metadatas.append(g.get("metadata", {}))
            ids.append(str(g["id"]))
            names.append(g["name"])

        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
            names=names
        )

    def search(self, query: str, n_results: int = 10) -> list[dict]:
        """Chercher des jeux similaires"""
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results
        )

        search_results = []
        for i in range(len(results["ids"][0])):
            result_item = {
                "id": results["ids"][0][i],
                "name": results["names"][0][i] if "names" in results else None,
                "distance": results["distances"][0][i],
                "metadata": results["metadatas"][0][i]
            }
            search_results.append(result_item)
        return search_results

    def persist(self):
        """Sauvegarder Chroma"""
        self.client.persist()
