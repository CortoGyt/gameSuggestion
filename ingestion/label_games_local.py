"""Outils partagés pour étiqueter les jeux (difficulté, exécution, hasard, glitchs) avec un modèle LOCAL (Ollama).

Ce fichier ne lance rien tout seul. Il fournit :
- build_prompt : le texte envoyé au modèle (en anglais : c'est ainsi qu'il a été mesuré) ;
- check_ollama : vérifie qu'Ollama répond et que le modèle est installé ;
- load_categories : les catégories de speedrun de chaque jeu ;
- get_pending_games : les jeux à étiqueter, avec leurs infos (genres, dimension, durée du record) ;
- save_labels : écrit les 4 niveaux (bas / moyen / haut) dans la table Games.

L'étiquetage lui-même (scores de 1 à 10, puis découpage par rang) est dans label_games_scores.py.
Variable d'environnement (facultative) : OLLAMA_URL (par défaut http://localhost:11434).
"""
import json
import os

import requests
from sqlalchemy import text

from ingestion.ingest_igdb import normalize

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
RAW_PATH = "data/speedrun_raw.json"
DEFAULT_CATEGORY = "Any%"

# Les trois niveaux, du plus bas au plus haut (les mêmes pour les quatre critères)
LEVELS = ["bas", "moyen", "haut"]


def load_categories() -> dict:
    """Nom de jeu normalisé -> catégories de speedrun, lues dans le fichier d'ingestion speedrun.com (s'il existe)."""
    categories = {}
    if not os.path.exists(RAW_PATH):
        return categories
    with open(RAW_PATH, encoding="utf-8") as f:
        data = json.load(f)
    for item in data:
        found = item.get("categories", [])
        if found:
            categories[normalize(item["game_name"])] = found
    return categories


def build_prompt(name: str, categories: list, genres, dimension, length_minutes, with_reasoning: bool = False, description=None) -> str:
    categories_text = ", ".join(categories)

    keys_text = "exactly these 4 keys"
    reasoning_text = ""
    if with_reasoning:
        keys_text = 'exactly these 5 keys, in this order: "reasoning" first, then the 4 labels'
        reasoning_text = (
            '"reasoning": 2 or 3 short sentences written BEFORE the labels. Say what you know about the speedruns '
            "of this game: the glitches and skips used, the RNG elements, the execution demands. "
            "If you do not know its speedruns well, say so and judge from its genre and mechanics.\n\n"
        )

    context = ""
    if genres:
        context += f"Genres: {genres}\n"
    if dimension:
        context += f"Dimension: {dimension}\n"
    if length_minutes:
        context += f"World record time of the main category: about {length_minutes} minutes\n"
    if description:
        context += f"Description: {description}\n"
    if context:
        context = "Known facts about the game:\n" + context + "\n"

    return f"""You are a video game and speedrunning expert. Analyze the game "{name}" with its speedrun categories: {categories_text}

{context}Respond ONLY with valid JSON containing {keys_text} (no other text).
Give exactly ONE overall assessment for the whole game, even if multiple categories are listed. Return a single flat JSON object.

What each key measures, for a SPEEDRUN of the game, and what each level means:

{reasoning_text}
"difficulty": how hard it is overall to learn and complete a good run (knowledge, practice time, consistency, resets, luck)
  facile = short and forgiving run, almost nothing to learn, a mistake costs almost nothing (example: Peggle)
  intermediaire = needs the route and some practice, resets are rare
  avance = a lot of practice or a long route to master
  difficile = hundreds of hours, frequent resets, a very demanding run
  extreme = the hardest runs that exist, because of the skill or because of luck that forces a huge number of attempts (example: Yu-Gi-Oh! Forbidden Memories)

"execution": how demanding the mechanical skill of the world-record route is (precise inputs, tricks, timing). This is NOT how hard the game is for a normal player.
  facile = simple inputs, no tight timing
  intermediaire = a few tricks with a comfortable timing margin
  avance = regular precise movement and tricks, but one mistake does not ruin the run
  difficile = many tight, frame-precise tricks, or glitch setups that must be executed exactly
  extreme = pixel-precise or frame-perfect inputs during most of the run, the top of what players can execute

"randomness": how much luck (RNG) can change the outcome or the time of a run
  aucun = the run is identical every time, no RNG
  bas = small RNG effects that rarely change the run
  moyen = RNG regularly changes the route or the time, the runner must adapt
  haut = RNG strongly decides the run, many resets are expected
  extreme = the run is mostly luck-driven

"glitchness": how much the run relies on glitches, exploits and out-of-bounds tricks
  aucun = no glitches, the game is played as intended
  bas = a few minor skips or tricks
  moyen = several glitches or skips, but the game is still mostly played normally
  haut = glitches are central to the run (major skips, out-of-bounds, wrong warps)
  extreme = the run is built almost entirely on glitches (for example arbitrary code execution)

Judge each of the 4 keys on its own, for the speedrun of this game, and use every level of the scales when the game calls for it.

SCALE A (use ONLY for difficulty and execution): facile, intermediaire, avance, difficile, extreme
SCALE B (use ONLY for randomness and glitchness): aucun, bas, moyen, haut, extreme

NEVER use a SCALE B word for difficulty or execution. NEVER use a SCALE A word for randomness or glitchness.
Keep the French words exactly as written above, even though these instructions are in English. Do not translate them.

Analysis for: {name}
Categories: {categories_text}"""


def check_ollama(model: str) -> bool:
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
    except Exception as exc:
        print(f"Ollama ne répond pas sur {OLLAMA_URL} ({exc}). Lance-le (`ollama serve`) puis réessaie.")
        return False
    installed = []
    for m in resp.json().get("models", []):
        installed.append(m["name"])
    for name in installed:
        if name == model or name.startswith(model + ":") or name.split(":")[0] == model:
            return True
    print(f"Le modèle '{model}' n'est pas installé. Lance : ollama pull {model}")
    print("Modèles installés :", ", ".join(installed) if installed else "(aucun)")
    return False


def get_pending_games(engine, limit: int | None, redo: bool, names: list | None = None) -> list:
    """Jeux à étiqueter. Si names est donné : exactement ces jeux, déjà étiquetés ou non."""
    where = ""
    params = {}
    if names:
        placeholders = []
        for i, game_name in enumerate(names):
            key = f"n{i}"
            placeholders.append(f":{key}")
            params[key] = game_name
        where = "WHERE g.game_name IN (" + ", ".join(placeholders) + ")"
    elif not redo:
        where = (
            "WHERE g.difficulty IS NULL OR g.execution IS NULL "
            "OR g.randomness IS NULL OR g.glitchness IS NULL"
        )
    sql = (
        "SELECT g.id, g.game_name, g.game_dimension, g.game_length, "
        "GROUP_CONCAT(s.style_name SEPARATOR ', ') AS styles "
        "FROM Games g "
        "LEFT JOIN Style_Games sg ON sg.game_id = g.id "
        "LEFT JOIN Styles s ON s.id = sg.style_id "
        f"{where} GROUP BY g.id ORDER BY g.id"
    )
    if limit:
        sql += " LIMIT :limit"
        params["limit"] = limit
    with engine.connect() as conn:
        return list(conn.execute(text(sql), params).fetchall())


def save_labels(engine, game_id: int, labels: dict) -> None:
    """Écrit les 4 niveaux (les mots bas / moyen / haut) d'un jeu dans la table Games."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE Games SET difficulty = :d, execution = :e, "
                "randomness = :r, glitchness = :g WHERE id = :id"
            ),
            {
                "d": labels["difficulty"],
                "e": labels["execution"],
                "r": labels["randomness"],
                "g": labels["glitchness"],
                "id": game_id,
            },
        )
