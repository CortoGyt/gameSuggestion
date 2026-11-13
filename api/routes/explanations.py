from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.database import get_db
from api.routes.games import get_styles_by_game
from api.routes.preferences import lire_preferences
from api.security import utilisateur_courant
from ml.rag import llm_client
from ml.rag.prompt import construire_prompt
from ml.vector.chromadb_vector import ChromaStore

router = APIRouter()

NB_EXTRAITS = 3


class ExplicationOut(BaseModel):
    game_id: int
    game_name: str
    explanation: str
    sources: list[str]  # d'où viennent les extraits (steam_description, igdb_summary...)


@lru_cache
def obtenir_store():
    # Créé au premier appel seulement : le chargement du modèle d'embedding prend quelques secondes
    return ChromaStore()


def obtenir_llm():
    return llm_client.generer


@router.get("/recommendations/{game_id}/explanation", response_model=ExplicationOut)
def expliquer_recommandation(
    game_id: int,
    utilisateur: dict = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
    store=Depends(obtenir_store),
    generer=Depends(obtenir_llm),
):
    ligne = db.execute(
        text(
            "SELECT g.game_name, d.label AS difficulte, r.label AS hasard FROM Games g "
            "LEFT JOIN EchellesDE d ON d.id = g.difficulty_id "
            "LEFT JOIN EchellesRG r ON r.id = g.randomness_id WHERE g.id = :id"
        ),
        {"id": game_id},
    ).fetchone()
    if ligne is None:
        raise HTTPException(status_code=404, detail="Jeu introuvable")
    styles_du_jeu = get_styles_by_game(db, [game_id]).get(game_id, [])
    jeu = {"nom": ligne.game_name, "styles": styles_du_jeu, "difficulte": ligne.difficulte, "hasard": ligne.hasard}

    saisies = lire_preferences(utilisateur, db)
    preferences = {"styles": saisies.styles, "difficulte": saisies.difficulty, "hasard": saisies.randomness}

    # La requête de recherche reprend le nom du jeu et ses styles
    requete = ligne.game_name + " " + ", ".join(styles_du_jeu)
    morceaux = store.search(requete, n_results=NB_EXTRAITS, game_id=game_id)
    extraits = []
    sources = []
    for morceau in morceaux:
        extraits.append(morceau["text"])
        if morceau["source"] not in sources:
            sources.append(morceau["source"])

    try:
        explication = generer(construire_prompt(jeu, preferences, extraits))
    except llm_client.LlmIndisponible:
        raise HTTPException(status_code=503, detail="Service d'explication indisponible")
    return {"game_id": game_id, "game_name": ligne.game_name, "explanation": explication, "sources": sources}
