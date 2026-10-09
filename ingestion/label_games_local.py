"""Label every game (difficulty, execution, randomness, glitchness) with a LOCAL model served by Ollama.

No training here: a pre-trained model is run on the GPU (inference) and its answers go to MySQL.
The answer format is enforced by Ollama with a JSON schema (enum of the allowed words), so the
model cannot output a word outside its scale or put a SCALE B word in "difficulty".

For each game that is not fully labelled yet, the prompt gets the game name, the speedrun categories
(from data/speedrun_raw.json when the game is in it, otherwise "Any%"), and, when the database has them,
the genres, the dimension and the world-record time. Then the four labels are stored as foreign keys
(Games.difficulty_id / execution_id -> EchellesDE, randomness_id / glitchness_id -> EchellesRG).

Usage (from the project root, Ollama running, model pulled with `ollama pull qwen2.5:14b`):
    python -m ingestion.label_games_local --limit 10 --dry-run   # look at the answers, write nothing
    python -m ingestion.label_games_local --dry-run --game Celeste --game "Hollow Knight"   # chosen games only
    python -m ingestion.label_games_local --dry-run --reasoning --game Tetris   # the model explains first
    python -m ingestion.label_games_local --limit 10             # write 10 games
    python -m ingestion.label_games_local                        # every game not labelled yet (resumable)
    python -m ingestion.label_games_local --redo                 # relabel everything (new model, new prompt)
    python -m ingestion.label_games_local --model mistral-small:24b

Every answer is also saved in data/labels_output.json so you can check them against what you know.
Env var (optional): OLLAMA_URL (default http://localhost:11434). Database: get_settings().DATABASE_URL.
"""
import argparse
import json
import os
import time

import requests
from config.settings import get_settings
from sqlalchemy import create_engine, text

from ingestion.ingest_igdb import normalize

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = "qwen2.5:14b"
RAW_PATH = "data/speedrun_raw.json"
OUTPUT_PATH = "data/labels_output.json"
DEFAULT_CATEGORY = "Any%"

SCALE_A = ["facile", "intermediaire", "avance", "difficile", "extreme"]
SCALE_B = ["aucun", "bas", "moyen", "haut", "extreme"]

# Ollama "structured output": the model can only produce this exact JSON shape and these words.
SCHEMA = {
    "type": "object",
    "properties": {
        "difficulty": {"type": "string", "enum": SCALE_A},
        "execution": {"type": "string", "enum": SCALE_A},
        "randomness": {"type": "string", "enum": SCALE_B},
        "glitchness": {"type": "string", "enum": SCALE_B},
    },
    "required": ["difficulty", "execution", "randomness", "glitchness"],
}


def make_schema(with_reasoning: bool) -> dict:
    """The schema above, with a free-text "reasoning" written BEFORE the four labels if asked."""
    if not with_reasoning:
        return SCHEMA
    properties = {"reasoning": {"type": "string"}}
    for key, value in SCHEMA["properties"].items():
        properties[key] = value
    required = ["reasoning"] + SCHEMA["required"]
    return {"type": "object", "properties": properties, "required": required}


def load_categories() -> dict:
    """normalized game name -> speedrun categories, from the speedrun.com ingestion file (if any)."""
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


def build_prompt(name: str, categories: list, genres, dimension, length_minutes, with_reasoning: bool = False) -> str:
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
    if context:
        context = "Known facts about the game:\n" + context + "\n"

    return f"""You are a video game and speedrunning expert. Analyze the game "{name}" with its speedrun categories: {categories_text}

{context}Respond ONLY with valid JSON containing {keys_text} (no other text).
Give exactly ONE overall assessment for the whole game, even if multiple categories are listed. Return a single flat JSON object.

What each key measures, for a SPEEDRUN of the game, and what each level means:

{reasoning_text}
"difficulty": how hard it is overall to learn and complete a good run (knowledge, practice time, consistency, resets, luck)
  facile = short and forgiving run, almost nothing to learn, a mistake costs almost nothing (examples: Peggle, Untitled Goose Game, Firewatch)
  intermediaire = needs the route and some practice, resets are rare
  avance = a lot of practice or a long route to master
  difficile = hundreds of hours, frequent resets, a very demanding run
  extreme = the hardest runs that exist, because of the skill or because of luck that forces a huge number of attempts (examples: Yu-Gi-Oh! Forbidden Memories, N++, Super Meat Boy, Ghosts 'n Goblins)

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


def ask_model(model: str, prompt: str, schema: dict = SCHEMA) -> dict:
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": schema,
            "options": {"temperature": 0},
        },
        timeout=600,  # the first call also loads the model into VRAM
    )
    resp.raise_for_status()
    return json.loads(resp.json()["message"]["content"])


def validate(result: dict) -> dict | None:
    """The labels as clean lowercase words if everything is valid, otherwise None."""
    clean = {}
    for key in ("difficulty", "execution", "randomness", "glitchness"):
        value = result.get(key)
        if not isinstance(value, str):
            return None
        clean[key] = normalize(value)
    for key in ("difficulty", "execution"):
        if clean[key] not in SCALE_A:
            return None
    for key in ("randomness", "glitchness"):
        if clean[key] not in SCALE_B:
            return None
    return clean


def get_scale_ids(engine, table: str) -> dict:
    """normalized label ('intermediaire') -> id, whatever the casing / accents stored in the table."""
    ids = {}
    with engine.connect() as conn:
        for row in conn.execute(text(f"SELECT id, label FROM {table}")).fetchall():
            ids[normalize(row[1])] = row[0]
    return ids


def get_pending_games(engine, limit: int | None, redo: bool, names: list | None = None) -> list:
    """Games to label. If names is given: exactly these games, labelled or not."""
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
            "WHERE g.difficulty_id IS NULL OR g.execution_id IS NULL "
            "OR g.randomness_id IS NULL OR g.glitchness_id IS NULL"
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


def save_labels(engine, game_id: int, labels: dict, ids_de: dict, ids_rg: dict) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE Games SET difficulty_id = :d, execution_id = :e, "
                "randomness_id = :r, glitchness_id = :g WHERE id = :id"
            ),
            {
                "d": ids_de[labels["difficulty"]],
                "e": ids_de[labels["execution"]],
                "r": ids_rg[labels["randomness"]],
                "g": ids_rg[labels["glitchness"]],
                "id": game_id,
            },
        )


def write_output(output: list) -> None:
    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="max games to process")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default {DEFAULT_MODEL})")
    parser.add_argument("--dry-run", action="store_true", help="show the answers, write nothing in the database")
    parser.add_argument("--redo", action="store_true", help="also relabel the games that already have labels")
    parser.add_argument(
        "--reasoning",
        action="store_true",
        help="the model first writes 2-3 sentences about the game's speedruns, then the labels (slower, often better)",
    )
    parser.add_argument(
        "--game",
        action="append",
        default=None,
        help="label only this game (exact name); repeat the option for several games",
    )
    args = parser.parse_args()

    if not check_ollama(args.model):
        return

    engine = create_engine(get_settings().DATABASE_URL)
    try:
        ids_de = get_scale_ids(engine, "EchellesDE")
        ids_rg = get_scale_ids(engine, "EchellesRG")
        missing = []
        for word in SCALE_A:
            if word not in ids_de:
                missing.append(f"EchellesDE:{word}")
        for word in SCALE_B:
            if word not in ids_rg:
                missing.append(f"EchellesRG:{word}")
        if missing:
            print("Valeurs absentes des tables d'échelles :", ", ".join(missing))
            return

        categories = load_categories()
        pending = get_pending_games(engine, args.limit, args.redo, args.game)
        print(f"{len(pending)} jeux à labelliser avec {args.model}" + (" (dry-run)" if args.dry_run else ""))

        output = []
        failed = 0
        started = time.time()
        try:
            for i, row in enumerate(pending, 1):
                game_id, name, dimension, length, genres = row
                name = name.strip()
                game_categories = categories.get(normalize(name), [DEFAULT_CATEGORY])
                prompt = build_prompt(name, game_categories, genres, dimension, length, args.reasoning)
                reasoning = None
                try:
                    answer = ask_model(args.model, prompt, make_schema(args.reasoning))
                    reasoning = answer.get("reasoning")
                    labels = validate(answer)
                    if labels is None:
                        raise ValueError("réponse invalide")
                    if not args.dry_run:
                        save_labels(engine, game_id, labels, ids_de, ids_rg)
                except Exception as exc:  # model/DB error: skip, retried on the next run
                    failed += 1
                    print(f"[{i}/{len(pending)}] ERREUR {name}: {exc}")
                    continue
                entry = {"game_id": game_id, "game_name": name, "model": args.model, **labels}
                if reasoning:
                    entry["reasoning"] = reasoning
                output.append(entry)
                print(
                    f"[{i}/{len(pending)}] {name}: diff={labels['difficulty']} exec={labels['execution']} "
                    f"rng={labels['randomness']} glitch={labels['glitchness']}"
                )
                if reasoning:
                    print(f"      {reasoning}")
        finally:
            write_output(output)
        minutes = round((time.time() - started) / 60, 1)
        print(f"Terminé en {minutes} min : {len(output)} labellisés, {failed} erreurs. Détail : {OUTPUT_PATH}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()