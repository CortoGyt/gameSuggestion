IDENTIFIANTS = {"user_name": "michel", "password": "motdepasse123"}


def connecter(client):
    client.post("/api/v1/auth/register", json=IDENTIFIANTS)
    jeton = client.post("/api/v1/auth/login", json=IDENTIFIANTS).json()["access_token"]
    return {"Authorization": "Bearer " + jeton}


def test_les_preferences_enregistrees_sont_relues(client):
    entetes = connecter(client)
    envoyees = {"styles": ["Platformer", "Puzzle"], "difficulty": "Avancé", "randomness": "Aucun"}
    assert client.put("/api/v1/preferences", json=envoyees, headers=entetes).status_code == 200
    relues = client.get("/api/v1/preferences", headers=entetes).json()
    assert relues["styles"] == ["Platformer", "Puzzle"]
    assert relues["difficulty"] == "Avancé"
    assert relues["randomness"] == "Aucun"
