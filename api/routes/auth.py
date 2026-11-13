from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.database import get_db
from api.security import (
    LONGUEUR_MAX_MOT_DE_PASSE,
    creer_jeton,
    hacher_mot_de_passe,
    utilisateur_courant,
    verifier_mot_de_passe,
)

router = APIRouter()


class InscriptionIn(BaseModel):
    user_name: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)


class ConnexionIn(BaseModel):
    user_name: str
    password: str


class JetonOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UtilisateurOut(BaseModel):
    id: int
    user_name: str
    role: str


@router.post("/auth/register", response_model=UtilisateurOut, status_code=201)
def inscription(donnees: InscriptionIn, db: Session = Depends(get_db)):
    if len(donnees.password.encode("utf-8")) > LONGUEUR_MAX_MOT_DE_PASSE:
        raise HTTPException(status_code=422, detail="Mot de passe trop long (72 octets maximum)")
    try:
        db.execute(
            text(
                "INSERT INTO Users (user_name, user_pw_hash, role_id) "
                "VALUES (:nom, :hash, (SELECT id FROM Roles WHERE name = 'user'))"
            ),
            {"nom": donnees.user_name, "hash": hacher_mot_de_passe(donnees.password)},
        )
        db.commit()
    except IntegrityError:
        # user_name est UNIQUE en base
        db.rollback()
        raise HTTPException(status_code=409, detail="Ce nom d'utilisateur existe déjà")
    ligne = db.execute(
        text("SELECT id FROM Users WHERE user_name = :nom"), {"nom": donnees.user_name}
    ).fetchone()
    return {"id": ligne.id, "user_name": donnees.user_name, "role": "user"}


@router.post("/auth/login", response_model=JetonOut)
def connexion(donnees: ConnexionIn, db: Session = Depends(get_db)):
    ligne = db.execute(
        text("SELECT id, user_pw_hash FROM Users WHERE user_name = :nom"),
        {"nom": donnees.user_name},
    ).fetchone()
    # Même message que le compte existe ou non, pour ne pas révéler quels noms existent
    if ligne is None or not verifier_mot_de_passe(donnees.password, ligne.user_pw_hash):
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    return {"access_token": creer_jeton(ligne.id)}


@router.get("/auth/me", response_model=UtilisateurOut)
def moi(utilisateur: dict = Depends(utilisateur_courant)):
    return utilisateur
