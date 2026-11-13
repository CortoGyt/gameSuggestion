import hashlib

from chromadb import Documents, EmbeddingFunction, Embeddings

from ml.vector.chromadb_vector import ChromaStore, chunk_text

DIMENSIONS = 64


class FakeEmbedding(EmbeddingFunction):
    # Embedding de test: sac de mots haché, sans téléchargement de modèle
    def __init__(self):
        pass

    def __call__(self, input: Documents) -> Embeddings:
        vectors = []
        for document in input:
            vector = [0.0] * DIMENSIONS
            for word in document.lower().split():
                slot = int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMENSIONS
                vector[slot] += 1.0
            vectors.append(vector)
        return vectors

    @staticmethod
    def name():
        return "fake-bag-of-words"

    def get_config(self):
        return {}

    @staticmethod
    def build_from_config(config):
        return FakeEmbedding()


def make_store(tmp_path):
    return ChromaStore(path=str(tmp_path), collection_name="test", embedding_function=FakeEmbedding())


def test_chunk_text_splits_lines_and_long_lines():
    chunks = chunk_text("first review\n\nsecond review\n" + "word " * 400, max_chars=100)
    assert chunks[0] == "first review"
    assert chunks[1] == "second review"
    assert len(chunks) > 3
    for chunk in chunks:
        assert len(chunk) <= 100


def test_search_returns_the_closest_game(tmp_path):
    store = make_store(tmp_path)
    store.upsert_texts(
        [
            {"game_id": 1, "game_name": "Celeste", "source": "steam_blurb", "content": "precise platformer climbing a mountain"},
            {"game_id": 2, "game_name": "Hades", "source": "steam_blurb", "content": "roguelike dungeon crawler in the underworld"},
        ]
    )
    results = store.search("mountain platformer", n_results=2)
    assert results[0]["game_name"] == "Celeste"
    assert results[0]["distance"] < results[1]["distance"]


def test_upsert_is_idempotent(tmp_path):
    store = make_store(tmp_path)
    item = {"game_id": 1, "game_name": "Celeste", "source": "steam_blurb", "content": "a mountain\nanother line"}
    store.upsert_texts([item])
    store.upsert_texts([item])
    assert store.count() == 2


def test_source_filter(tmp_path):
    store = make_store(tmp_path)
    store.upsert_texts(
        [
            {"game_id": 1, "game_name": "Celeste", "source": "steam_blurb", "content": "mountain climbing"},
            {"game_id": 1, "game_name": "Celeste", "source": "steam_reviews", "content": "great mountain game"},
        ]
    )
    results = store.search("mountain", n_results=5, source="steam_reviews")
    assert len(results) == 1
    assert results[0]["source"] == "steam_reviews"


def test_reset_empties_the_index(tmp_path):
    store = make_store(tmp_path)
    store.upsert_texts([{"game_id": 1, "game_name": "Celeste", "source": "steam_blurb", "content": "mountain"}])
    store.reset()
    assert store.count() == 0