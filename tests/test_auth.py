from sqlalchemy import text

IDENTIFIANTS = {"user_name": "michel", "password": "motdepasse123"}


def test_inscription_puis_connexion_donne_un_jeton_qui_ouvre_auth_me(client):
    assert client.post("/api/v1/auth/register", json=IDENTIFIANTS).status_code == 201
    reponse = client.post("/api/v1/auth/login", json=IDENTIFIANTS)
    assert reponse.status_code == 200
    jeton = reponse.json()["access_token"]
    moi = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + jeton})
    assert moi.status_code == 200
    assert moi.json()["user_name"] == "michel"


def test_mauvais_mot_de_passe_ou_nom_inconnu_donnent_la_meme_erreur_401(client):
    client.post("/api/v1/auth/register", json=IDENTIFIANTS)
    mauvais_mdp = client.post("/api/v1/auth/login", json={**IDENTIFIANTS, "password": "autre-chose"})
    inconnu = client.post("/api/v1/auth/login", json={"user_name": "personne", "password": "x"})
    assert mauvais_mdp.status_code == 401
    assert inconnu.status_code == 401
    assert mauvais_mdp.json() == inconnu.json()


def test_le_mot_de_passe_n_est_jamais_stocke_en_clair(client):
    from api.database import get_db
    from main import app

    client.post("/api/v1/auth/register", json=IDENTIFIANTS)
    db = next(app.dependency_overrides[get_db]())
    hash_stocke = db.execute(text("SELECT user_pw_hash FROM Users")).scalar()
    assert hash_stocke != IDENTIFIANTS["password"]
    assert hash_stocke.startswith("$2")  # empreinte bcrypt
