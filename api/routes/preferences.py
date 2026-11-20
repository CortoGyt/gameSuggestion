from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.database import get_db
from api.security import utilisateur_courant

router = APIRouter()

class PreferencesIn(BaseModel):
    styles: list[str] = Field(default=[], max_length=20)
    difficulty: Literal["bas", "moyen", "haut"] | None = None
    execution: Literal["bas", "moyen", "haut"] | None = None
    randomness: Literal["bas", "moyen", "haut"] | None = None
    glitchness: Literal["bas", "moyen", "haut"] | None = None
    duration: Literal["court", "moyen", "long"] | None = None
    dimension: Literal["2D", "2.5D", "3D"] | None = None


def trouver_id(db, requete, valeur, nom_du_champ):
    # Id d'un style à partir de son nom ; None si aucune valeur ; 422 si le nom n'existe pas
    if valeur is None:
        return None
    ligne = db.execute(text(requete), {"label": valeur}).fetchone()
    if ligne is None:
        raise HTTPException(status_code=422, detail="Valeur inconnue pour " + nom_du_champ + " : " + valeur)
    return ligne.id


@router.put("/preferences", response_model=PreferencesIn)
def enregistrer_preferences(
    donnees: PreferencesIn,
    utilisateur: dict = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    user_id = utilisateur["id"]
    ids_styles = []
    for nom in donnees.styles:
        id_style = trouver_id(db, "SELECT id FROM Styles WHERE style_name = :label", nom, "styles")
        if id_style not in ids_styles:
            ids_styles.append(id_style)

    # On remplace toutes les préférences précédentes de l'utilisateur
    db.execute(text("DELETE FROM Preferences_Styles WHERE user_id = :id"), {"id": user_id})
    db.execute(text("DELETE FROM Preferences WHERE user_id = :id"), {"id": user_id})
    db.execute(
        text(
            "INSERT INTO Preferences (user_id, duration_pref, dimension_pref, difficulty, "
            "execution, randomness, glitchness) "
            "VALUES (:id, :duree, :dimension, :diff, :exec, :hasard, :glitch)"
        ),
        {
            "id": user_id,
            "duree": donnees.duration,
            "dimension": donnees.dimension,
            "diff": donnees.difficulty,
            "exec": donnees.execution,
            "hasard": donnees.randomness,
            "glitch": donnees.glitchness,
        },
    )
    for id_style in ids_styles:
        db.execute(
            text("INSERT INTO Preferences_Styles (user_id, style_id) VALUES (:id, :style)"),
            {"id": user_id, "style": id_style},
        )
    db.commit()
    return donnees


@router.get("/preferences", response_model=PreferencesIn)
def lire_preferences(
    utilisateur: dict = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    user_id = utilisateur["id"]
    ligne = db.execute(
        text(
            "SELECT p.duration_pref, p.dimension_pref, p.difficulty, p.execution, "
            "p.randomness, p.glitchness "
            "FROM Preferences p "
            "WHERE p.user_id = :id"
        ),
        {"id": user_id},
    ).fetchone()
    if ligne is None:
        return PreferencesIn()
    styles = []
    for style in db.execute(
        text(
            "SELECT s.style_name FROM Preferences_Styles ps "
            "JOIN Styles s ON s.id = ps.style_id WHERE ps.user_id = :id ORDER BY s.style_name"
        ),
        {"id": user_id},
    ):
        styles.append(style.style_name)
    return PreferencesIn(
        styles=styles,
        difficulty=ligne.difficulty,
        execution=ligne.execution,
        randomness=ligne.randomness,
        glitchness=ligne.glitchness,
        duration=ligne.duration_pref,
        dimension=ligne.dimension_pref,
    )
