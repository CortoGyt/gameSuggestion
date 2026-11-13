from api.routes.explanations import obtenir_llm, obtenir_store
from main import app

IDENTIFIANTS = {"user_name": "michel", "password": "motdepasse123"}


class FauxStore:
    def search(self, requete, n_results, game_id):
        return [{"text": "A tough but fair platformer about climbing a mountain.", "source": "igdb_summary"}]


def test_l_explication_est_construite_avec_les_extraits_du_jeu_et_les_gouts_du_joueur(client):
    client.post("/api/v1/auth/register", json=IDENTIFIANTS)
    jeton = client.post("/api/v1/auth/login", json=IDENTIFIANTS).json()["access_token"]
    entetes = {"Authorization": "Bearer " + jeton}
    client.put("/api/v1/preferences", json={"styles": ["Platformer"], "difficulty": "Avancé"}, headers=entetes)

    prompts_recus = []

    def faux_llm(prompt):
        prompts_recus.append(prompt)
        return "Celeste est un platformer exigeant, comme tu l'aimes."

    app.dependency_overrides[obtenir_store] = lambda: FauxStore()
    app.dependency_overrides[obtenir_llm] = lambda: faux_llm
    reponse = client.get("/api/v1/recommendations/1/explanation", headers=entetes)

    assert reponse.status_code == 200
    assert reponse.json()["explanation"].startswith("Celeste")
    assert reponse.json()["sources"] == ["igdb_summary"]
    # Le prompt contient bien le jeu, les extraits et les goûts du joueur
    assert "Celeste" in prompts_recus[0]
    assert "climbing a mountain" in prompts_recus[0]
    assert "Platformer" in prompts_recus[0]
