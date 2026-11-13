from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from api.database import get_db
from api.security import utilisateur_courant
from config.settings import get_settings
from ml.cold_start import classer_jeux
from ml.svd.model import SvdModel

router = APIRouter()


class RecommandationOut(BaseModel):
    game_id: int
    game_name: str
    predicted_rating: float
    source: str  # "svd" (d'après ses notes) ou "preferences" (démarrage à froid)


@lru_cache
def _charger(chemin):
    # Le fichier n'est lu qu'une fois : relancer l'API après un nouvel entraînement
    return SvdModel.load(chemin)


def charger_modele():
    # None si le modèle n'existe pas encore (le démarrage à froid fonctionne sans lui)
    try:
        return _charger(get_settings().SVD_MODEL_PATH)
    except FileNotFoundError:
        return None


def charger_preferences(db, user_id):
    ligne = db.execute(
        text("SELECT difficulty_id, randomness_id FROM Preferences WHERE user_id = :id"),
        {"id": user_id},
    ).fetchone()
    if ligne is None:
        return None
    styles = []
    for style in db.execute(
        text(
            "SELECT s.style_name FROM Preferences_Styles ps "
            "JOIN Styles s ON s.id = ps.style_id WHERE ps.user_id = :id"
        ),
        {"id": user_id},
    ):
        styles.append(style.style_name)
    return {"styles": styles, "difficulte": ligne.difficulty_id, "hasard": ligne.randomness_id}


def charger_jeux(db):
    jeux = {}
    for ligne in db.execute(text("SELECT id, game_name, difficulty_id, randomness_id FROM Games")):
        jeux[ligne.id] = {
            "id": ligne.id,
            "nom": ligne.game_name,
            "difficulte": ligne.difficulty_id,
            "hasard": ligne.randomness_id,
            "styles": [],
        }
    for ligne in db.execute(
        text("SELECT sg.game_id, s.style_name FROM Style_Games sg JOIN Styles s ON s.id = sg.style_id")
    ):
        if ligne.game_id in jeux:
            jeux[ligne.game_id]["styles"].append(ligne.style_name)
    return list(jeux.values())


def recommandations_depuis_svd(modele, db, user_id, n):
    couples = modele.recommend(user_id, n)
    if len(couples) == 0:
        return []
    ids = []
    for game_id, note in couples:
        ids.append(game_id)
    requete = text("SELECT id, game_name FROM Games WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    noms = {}
    for ligne in db.execute(requete, {"ids": ids}).fetchall():
        noms[ligne.id] = ligne.game_name
    resultat = []
    for game_id, note in couples:
        if game_id in noms:
            resultat.append(
                {"game_id": game_id, "game_name": noms[game_id], "predicted_rating": round(note, 2), "source": "svd"}
            )
    return resultat


def recommandations_depuis_preferences(db, user_id, n):
    preferences = charger_preferences(db, user_id)
    if preferences is None:
        return []
    resultat = []
    for jeu, score in classer_jeux(preferences, charger_jeux(db), n):
        resultat.append(
            {
                "game_id": jeu["id"],
                "game_name": jeu["nom"],
                "predicted_rating": round(1 + 4 * score, 2),  # score 0..1 ramené sur l'échelle 1..5
                "source": "preferences",
            }
        )
    return resultat


@router.get("/recommendations", response_model=list[RecommandationOut])
def recommandations(
    n: int = Query(10, ge=1, le=50),
    utilisateur: dict = Depends(utilisateur_courant),
    modele: SvdModel | None = Depends(charger_modele),
    db: Session = Depends(get_db),
):
    resultat = []
    if modele is not None:
        resultat = recommandations_depuis_svd(modele, db, utilisateur["id"], n)
    if len(resultat) == 0:
        # Aucune note connue du modèle : on se base sur les préférences de l'onboarding
        resultat = recommandations_depuis_preferences(db, utilisateur["id"], n)
    if len(resultat) == 0 and modele is None:
        raise HTTPException(
            status_code=503,
            detail="Modèle de recommandation indisponible : lancer python -m ml.svd.train",
        )
    return resultat
