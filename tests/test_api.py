def test_health(client):
    reponse = client.get("/api/v1/health")
    assert reponse.status_code == 200
    assert reponse.json() == {"status": "ok", "database": "ok"}


def test_liste_des_jeux(client):
    donnees = client.get("/api/v1/games").json()
    assert donnees["total"] == 3
    assert len(donnees["items"]) == 3
