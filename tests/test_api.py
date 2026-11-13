def test_health(client):
    reponse = client.get("/api/v1/health")
    assert reponse.status_code == 200
    assert reponse.json() == {"status": "ok", "database": "ok"}


def test_liste_des_jeux(client):
    donnees = client.get("/api/v1/games").json()
    assert donnees["total"] == 3
    assert len(donnees["items"]) == 3


def test_recherche_par_nom(client):
    donnees = client.get("/api/v1/games?q=cel").json()
    assert donnees["total"] == 1
    assert donnees["items"][0]["name"] == "Celeste"


def test_jeu_inexistant_renvoie_404(client):
    assert client.get("/api/v1/games/99999").status_code == 404


def test_limit_trop_grand_est_refuse(client):
    # La limite est plafonnée à 100 : au-dessus, FastAPI répond 422
    assert client.get("/api/v1/games?limit=500").status_code == 422
