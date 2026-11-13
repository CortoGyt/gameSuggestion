"""Index vectoriel des textes de jeux (ChromaDB persistant).

Les textes viennent de la table Textes (descriptions et avis Steam, résumés IGDB).
Chaque texte est découpé en morceaux courts, car le modèle d'embedding ne lit que
les premières centaines de caractères d'un document.

Sans embedding_function, Chroma utilise son modèle par défaut (all-MiniLM-L6-v2, en local,
téléchargé une seule fois au premier usage). Ce modèle comprend l'anglais : les textes et
les requêtes doivent donc être en anglais.
"""
import chromadb
from chromadb.config import Settings as ChromaSettings

from config.settings import get_settings

MAX_CHUNK_CHARS = 800


def chunk_text(content, max_chars=MAX_CHUNK_CHARS):
    # Une ligne = un morceau (un avis, un paragraphe) ; une ligne trop longue est coupée sur un espace
    chunks = []
    for line in content.split("\n"):
        line = line.strip()
        while len(line) > max_chars:
            cut = line.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            chunks.append(line[:cut].strip())
            line = line[cut:].strip()
        if line:
            chunks.append(line)
    return chunks


class ChromaStore:
    def __init__(self, path=None, collection_name=None, embedding_function=None):
        settings = get_settings()
        # Télémétrie coupée : aucune donnée d'usage n'est envoyée à l'extérieur
        self.client = chromadb.PersistentClient(
            path=path or settings.CHROMA_DB_PATH,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection_options = {
            "name": collection_name or settings.CHROMA_COLLECTION,
            "metadata": {"hnsw:space": "cosine"},
        }
        if embedding_function is not None:
            self.collection_options["embedding_function"] = embedding_function
        self.collection = self.client.get_or_create_collection(**self.collection_options)

    def upsert_texts(self, texts):
        # texts : [{"game_id", "game_name", "source", "content"}, ...]
        # Idempotent : relancer met à jour les morceaux existants au lieu de les dupliquer.
        ids = []
        documents = []
        metadatas = []
        for item in texts:
            index = 0
            for chunk in chunk_text(item["content"]):
                ids.append(str(item["game_id"]) + "-" + item["source"] + "-" + str(index))
                documents.append(chunk)
                metadatas.append(
                    {"game_id": item["game_id"], "game_name": item["game_name"], "source": item["source"]}
                )
                index += 1
        if len(ids) > 0:
            self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        return len(ids)

    def search(self, query, n_results=10, source=None, game_id=None):
        # Renvoie les morceaux les plus proches, du plus proche au plus éloigné
        # source et game_id sont des filtres facultatifs (les deux ensemble : les deux doivent correspondre)
        options = {"query_texts": [query], "n_results": n_results}
        conditions = []
        if source:
            conditions.append({"source": source})
        if game_id is not None:
            conditions.append({"game_id": game_id})
        if len(conditions) == 1:
            options["where"] = conditions[0]
        if len(conditions) == 2:
            options["where"] = {"$and": conditions}
        raw = self.collection.query(**options)
        results = []
        for i in range(len(raw["ids"][0])):
            metadata = raw["metadatas"][0][i]
            results.append(
                {
                    "id": raw["ids"][0][i],
                    "game_id": metadata["game_id"],
                    "game_name": metadata["game_name"],
                    "source": metadata["source"],
                    "text": raw["documents"][0][i],
                    "distance": raw["distances"][0][i],
                }
            )
        return results

    def count(self):
        return self.collection.count()

    def reset(self):
        # Vide la collection (même nom, mêmes réglages)
        self.client.delete_collection(self.collection_options["name"])
        self.collection = self.client.get_or_create_collection(**self.collection_options)