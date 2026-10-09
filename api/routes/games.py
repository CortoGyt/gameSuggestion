from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from api.database import get_db
from api.schemas import GameListOut, GameOut

router = APIRouter()

# Les libellés des échelles viennent des tables EchellesDE / EchellesRG
SELECT_GAMES = """
    SELECT g.id, g.game_name, g.game_length, g.game_dimension,
           d.label AS difficulty, e.label AS execution,
           r.label AS randomness, gl.label AS glitchness
    FROM Games g
    LEFT JOIN EchellesDE d ON d.id = g.difficulty_id
    LEFT JOIN EchellesDE e ON e.id = g.execution_id
    LEFT JOIN EchellesRG r ON r.id = g.randomness_id
    LEFT JOIN EchellesRG gl ON gl.id = g.glitchness_id
"""


def get_styles_by_game(db, game_ids):
    # {game_id: [noms de styles]} pour une liste de jeux, en une seule requête
    result = {}
    if len(game_ids) == 0:
        return result
    query = text(
        "SELECT sg.game_id, s.style_name FROM Style_Games sg "
        "JOIN Styles s ON s.id = sg.style_id "
        "WHERE sg.game_id IN :ids ORDER BY s.style_name"
    ).bindparams(bindparam("ids", expanding=True))
    for row in db.execute(query, {"ids": game_ids}):
        if row.game_id not in result:
            result[row.game_id] = []
        result[row.game_id].append(row.style_name)
    return result


def row_to_game(row, styles):
    return GameOut(
        id=row.id,
        name=row.game_name,
        length_minutes=row.game_length,
        dimension=row.game_dimension,
        difficulty=row.difficulty,
        execution=row.execution,
        randomness=row.randomness,
        glitchness=row.glitchness,
        styles=styles,
    )


@router.get("/games", response_model=GameListOut)
def list_games(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, max_length=100),
    style: str | None = Query(None, max_length=50),
    db: Session = Depends(get_db),
):
    where = " WHERE 1=1"
    params = {}
    if q:
        where += " AND g.game_name LIKE :q"
        params["q"] = "%" + q + "%"
    if style:
        where += (
            " AND g.id IN (SELECT sg.game_id FROM Style_Games sg "
            "JOIN Styles s ON s.id = sg.style_id WHERE s.style_name = :style)"
        )
        params["style"] = style

    total = db.execute(text("SELECT COUNT(*) FROM Games g" + where), params).scalar()

    params["limit"] = limit
    params["offset"] = offset
    rows = db.execute(
        text(SELECT_GAMES + where + " ORDER BY g.game_name LIMIT :limit OFFSET :offset"),
        params,
    ).fetchall()

    ids = []
    for row in rows:
        ids.append(row.id)
    styles = get_styles_by_game(db, ids)

    items = []
    for row in rows:
        items.append(row_to_game(row, styles.get(row.id, [])))
    return GameListOut(total=total, limit=limit, offset=offset, items=items)


@router.get("/games/{game_id}", response_model=GameOut)
def get_game(game_id: int, db: Session = Depends(get_db)):
    row = db.execute(text(SELECT_GAMES + " WHERE g.id = :id"), {"id": game_id}).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Jeu introuvable")
    styles = get_styles_by_game(db, [row.id])
    return row_to_game(row, styles.get(row.id, []))
