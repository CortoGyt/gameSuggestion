from pydantic import BaseModel


class GameOut(BaseModel):
    id: int
    name: str
    length_minutes: int | None = None
    dimension: str | None = None
    difficulty: str | None = None
    execution: str | None = None
    randomness: str | None = None
    glitchness: str | None = None
    styles: list[str] = []


class GameListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[GameOut]


class HealthOut(BaseModel):
    status: str
    database: str
