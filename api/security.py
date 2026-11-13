"""Mots de passe (bcrypt) et jetons JWT. Aucune route ici : seulement les outils de sécurité."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.database import get_db
from config.settings import get_settings

ALGORITHME = "HS256"
LONGUEUR_MAX_MOT_DE_PASSE = 72  # limite de bcrypt, en octets

# auto_error=False : c'est nous qui renvoyons l'erreur 401 (message clair)
schema_bearer = HTTPBearer(auto_error=False)


def hacher_mot_de_passe(mot_de_passe):
    return bcrypt.hashpw(mot_de_passe.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verifier_mot_de_passe(mot_de_passe, hash_enregistre):
    # Faux (et pas d'erreur) si le hash n'est pas valide, par exemple les comptes synth_*
    try:
        return bcrypt.checkpw(mot_de_passe.encode("utf-8"), hash_enregistre.encode("utf-8"))
    except ValueError:
        return False


def creer_jeton(user_id):
    settings = get_settings()
    expiration = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    contenu = {"sub": str(user_id), "exp": expiration}
    return jwt.encode(contenu, settings.JWT_SECRET_KEY, algorithm=ALGORITHME)


def utilisateur_courant(
    identifiants: HTTPAuthorizationCredentials | None = Depends(schema_bearer),
    db: Session = Depends(get_db),
):
    # Dépendance à ajouter aux routes protégées : renvoie l'utilisateur ou lève une 401
    erreur = HTTPException(
        status_code=401,
        detail="Connexion requise",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if identifiants is None:
        raise erreur
    try:
        contenu = jwt.decode(
            identifiants.credentials, get_settings().JWT_SECRET_KEY, algorithms=[ALGORITHME]
        )
    except jwt.PyJWTError:
        raise erreur
    ligne = db.execute(
        text(
            "SELECT u.id, u.user_name, r.name AS role FROM Users u "
            "JOIN Roles r ON r.id = u.role_id WHERE u.id = :id"
        ),
        {"id": int(contenu["sub"])},
    ).fetchone()
    if ligne is None:
        raise erreur
    return {"id": ligne.id, "user_name": ligne.user_name, "role": ligne.role}
