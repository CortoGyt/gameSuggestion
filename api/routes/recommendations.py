from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from api.database import get_db
from api.security import utilisateur_courant
from config.settings import get_settings
from ml.svd.model import SvdModel

router = APIRouter()


class RecommandationOut(BaseModel):
    game_id: int
    game_name: str
    predicted_rating: float


@lru_cache
def _charger(chemin):
    # Le fichier n'est lu qu'une fois : relancer l'API après un nouvel entraînement
    return SvdModel.load(chemin)


def charger_modele():
    chemin = get_settings().SVD_MODEL_PATH
    try:
        return _charger(chemin)
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Modèle de recommandation indisponible : lancer python -m ml.svd.train",
        )


@router.get("/recommendations", response_model=list[RecommandationOut])
def recommandations(
    n: int = Query(10, ge=1, le=50),
    utilisateur: dict = Depends(utilisateur_courant),
    modele: SvdModel = Depends(charger_modele),
    db: Session = Depends(get_db),
):
    # Un utilisateur sans notes (nouveau compte) reçoit une liste vide pour l'instant
    couples = modele.recommend(utilisateur["id"], n)
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
                {"game_id": game_id, "game_name": noms[game_id], "predicted_rating": round(note, 2)}
            )
    return resultat
