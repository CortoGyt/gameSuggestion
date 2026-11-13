from api.routes.recommendations import charger_modele
from main import app
from ml.svd.model import SvdModel

IDENTIFIANTS = {"user_name": "michel", "password": "motdepasse123"}


def connecter(client):
    client.post("/api/v1/auth/register", json=IDENTIFIANTS)
    jeton = client.post("/api/v1/auth/login", json=IDENTIFIANTS).json()["access_token"]
    return {"Authorization": "Bearer " + jeton}


def test_les_recommandations_excluent_les_jeux_deja_notes_et_donnent_le_nom(client):
    # L'utilisateur inscrit a l'id 1 : il a noté le jeu 1, il reste les jeux 2 et 3
    notes = [(1, 1, 5), (2, 1, 4), (2, 2, 4), (2, 3, 5)]
    app.dependency_overrides[charger_modele] = lambda: SvdModel(nb_facteurs=2).fit(notes)
    reponse = client.get("/api/v1/recommendations", headers=connecter(client))
    assert reponse.status_code == 200
    noms = []
    for jeu in reponse.json():
        noms.append(jeu["game_name"])
    assert sorted(noms) == ["Hades", "Peggle"]


def test_un_nouvel_utilisateur_avec_preferences_recoit_des_jeux_classes_par_ressemblance(client):
    entetes = connecter(client)
    preferences = {"styles": ["Platformer"], "difficulty": "Avancé", "randomness": "Aucun"}
    client.put("/api/v1/preferences", json=preferences, headers=entetes)
    notes = [(10, 1, 5), (10, 2, 3), (11, 3, 4)]
    app.dependency_overrides[charger_modele] = lambda: SvdModel(nb_facteurs=2).fit(notes)
    reponse = client.get("/api/v1/recommendations", headers=entetes).json()
    assert reponse[0]["game_name"] == "Celeste"
    assert reponse[0]["source"] == "preferences"
