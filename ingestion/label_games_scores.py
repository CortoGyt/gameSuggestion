"""Étiquette les jeux à partir de SCORES (1 à 10) au lieu de mots, puis transforme les scores en niveaux PAR RANG.

Pourquoi : avec des mots, le modèle local répond presque toujours le mot du milieu. Ici le modèle donne
un score de 1 à 10 pour chaque critère ; les jeux sont ensuite triés puis découpés en 3 niveaux
(bas / moyen / haut) avec des parts fixes (PROPORTIONS), donc les 3 niveaux sont toujours utilisés.
Les niveaux sont RELATIFS au catalogue : « haut » = parmi les 30 % de jeux les plus hauts.

Rien n'est écrit en base sans l'option --write.

Utilisation (depuis la racine du projet, Ollama lancé) :
    python -m ingestion.label_games_scores --limit 10            # test : 10 jeux, rien n'est écrit
    python -m ingestion.label_games_scores                       # note tous les jeux, affiche le résultat et la mesure sur ta référence
    python -m ingestion.label_games_scores --from-file           # réutilise data/scores_raw.json (aucun appel au modèle)
    python -m ingestion.label_games_scores --from-file --write   # écrit les niveaux dans MySQL
    python -m ingestion.label_games_scores --no-mlflow           # n'enregistre pas le run dans MLflow

Les scores bruts sont sauvegardés dans data/scores_raw.json : on peut refaire le découpage sans rappeler le modèle.
"""
import argparse
import json
import os
import time

import requests
from config.settings import get_settings
from sqlalchemy import create_engine, text

from ingestion.evaluate_labelling import (
    KEYS,
    REFERENCE_PATH,
    compute_metrics,
    load_reference,
    log_to_mlflow,
    scale_for,
)
from ingestion.ingest_igdb import normalize
from ingestion.label_games_local import (
    DEFAULT_CATEGORY,
    OLLAMA_URL,
    build_prompt,
    check_ollama,
    get_pending_games,
    load_categories,
    save_labels,
)

DEFAULT_MODEL = "mistral-small:24b"
SCORES_PATH = "data/scores_raw.json"
# part des jeux donnée à chacun des 3 niveaux, du plus bas au plus haut (somme = 1)
PROPORTIONS = [0.30, 0.40, 0.30]
SCORE_VALUES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "difficulty": {"type": "integer", "enum": SCORE_VALUES},
        "execution": {"type": "integer", "enum": SCORE_VALUES},
        "randomness": {"type": "integer", "enum": SCORE_VALUES},
        "glitchness": {"type": "integer", "enum": SCORE_VALUES},
    },
    "required": ["difficulty", "execution", "randomness", "glitchness"],
}


def build_score_prompt(name: str, categories: list, genres, dimension, length_minutes, description=None) -> str:
    """Le prompt d'étiquetage (mêmes définitions), avec le format de réponse changé en scores de 1 à 10."""
    base = build_prompt(name, categories, genres, dimension, length_minutes, False, description)
    definitions = base[: base.index("SCALE A (use ONLY")]
    categories_text = ", ".join(categories)
    return (
        definitions
        + "Answer with an integer SCORE from 1 to 10 for each of the 4 keys, NOT with words.\n"
        + "The 5 levels written above go from the lowest to the highest: scores 1-2 = the first level, "
        + "3-4 = the second, 5-6 = the third, 7-8 = the fourth, 9-10 = the fifth. "
        + "Use the two scores of a level to say whether the game is in the lower or the upper part of it.\n"
        + "Compare this game with all the other speedrun games you know.\n\n"
        + f"Analysis for: {name}\nCategories: {categories_text}"
    )


def get_description(engine, game_id: int) -> str:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT content FROM Textes WHERE game_id = :id "
                "AND source IN ('steam_blurb', 'igdb_summary') "
                "ORDER BY FIELD(source, 'steam_blurb', 'igdb_summary') LIMIT 1"
            ),
            {"id": game_id},
        ).fetchone()
    if row is None:
        return ""
    return row[0][:300].replace("\n", " ")


def ask_scores(model: str, prompt: str) -> dict:
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": SCORE_SCHEMA,
            "options": {"temperature": 0},
        },
        timeout=600,
    )
    resp.raise_for_status()
    return json.loads(resp.json()["message"]["content"])


def validate_scores(answer: dict) -> dict | None:
    clean = {}
    for key in KEYS:
        value = answer.get(key)
        if not isinstance(value, int) or value < 1 or value > 10:
            return None
        clean[key] = value
    return clean


def scores_to_levels(values: list) -> list:
    """Numéro de niveau (0 à 2) de chaque valeur, par rang. Deux scores égaux ont toujours le même niveau."""
    total = len(values)
    ordered = sorted(values)
    first = {}
    last = {}
    for index, value in enumerate(ordered):
        if value not in first:
            first[value] = index
        last[value] = index

    levels = []
    for value in values:
        middle = (first[value] + last[value]) / 2
        share = (middle + 0.5) / total
        cumulated = 0.0
        level = len(PROPORTIONS) - 1
        for position, proportion in enumerate(PROPORTIONS):
            cumulated += proportion
            if share <= cumulated:
                level = position
                break
        levels.append(level)
    return levels


def convert_all(scores: dict) -> dict:
    """{nom du jeu: {critère: score}} -> {nom du jeu: {critère: mot du niveau}}"""
    names = list(scores.keys())
    labels = {}
    for name in names:
        labels[name] = {}
    for key in KEYS:
        values = []
        for name in names:
            values.append(scores[name][key])
        levels = scores_to_levels(values)
        scale = scale_for(key)
        for i, name in enumerate(names):
            labels[name][key] = scale[levels[i]]
    return labels


def print_distribution(labels: dict) -> None:
    for key in KEYS:
        counts = {}
        for name in labels:
            word = labels[name][key]
            counts[word] = counts.get(word, 0) + 1
        parts = []
        for word in scale_for(key):
            parts.append(f"{word} {counts.get(word, 0)}")
        print(f"  {key:11} " + " | ".join(parts))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"modèle Ollama (par défaut {DEFAULT_MODEL})")
    parser.add_argument("--limit", type=int, default=None, help="nombre maximum de jeux à noter (test)")
    parser.add_argument("--from-file", action="store_true", help=f"réutilise {SCORES_PATH}, sans appeler le modèle")
    parser.add_argument("--write", action="store_true", help="écrit les niveaux dans la base de données")
    parser.add_argument("--reference", default=REFERENCE_PATH, help="tes labels attendus, pour mesurer le résultat")
    parser.add_argument("--no-mlflow", action="store_true", help="n'enregistre pas le run dans MLflow")
    args = parser.parse_args()

    engine = create_engine(get_settings().DATABASE_URL)
    try:
        games = {}  # nom -> (id, secondes)
        scores = {}
        seconds_total = 0.0

        if args.from_file:
            with open(SCORES_PATH, encoding="utf-8") as f:
                saved = json.load(f)
            for item in saved:
                scores[item["game_name"]] = item["scores"]
                games[item["game_name"]] = (item["game_id"], item.get("seconds", 0.0))
            print(f"{len(scores)} jeux lus dans {SCORES_PATH}")
        else:
            if not check_ollama(args.model):
                return
            categories = load_categories()
            pending = get_pending_games(engine, args.limit, True)
            print(f"{len(pending)} jeux à noter avec {args.model}")
            saved = []
            failed = 0
            try:
                for i, row in enumerate(pending, 1):
                    game_id, name, dimension, length, genres = row
                    name = name.strip()
                    game_categories = categories.get(normalize(name), [DEFAULT_CATEGORY])
                    description = get_description(engine, game_id)
                    prompt = build_score_prompt(name, game_categories, genres, dimension, length, description)
                    started = time.time()
                    try:
                        result = validate_scores(ask_scores(args.model, prompt))
                        if result is None:
                            raise ValueError("réponse invalide")
                    except Exception as exc:
                        failed += 1
                        print(f"[{i}/{len(pending)}] ERREUR {name}: {exc}")
                        continue
                    seconds = round(time.time() - started, 2)
                    scores[name] = result
                    games[name] = (game_id, seconds)
                    saved.append({"game_id": game_id, "game_name": name, "scores": result, "seconds": seconds})
                    print(
                        f"[{i}/{len(pending)}] {name}: diff={result['difficulty']} exec={result['execution']} "
                        f"rng={result['randomness']} glitch={result['glitchness']}"
                    )
            finally:
                os.makedirs("data", exist_ok=True)
                with open(SCORES_PATH, "w", encoding="utf-8") as f:
                    json.dump(saved, f, ensure_ascii=False, indent=2)
            print(f"{len(scores)} jeux notés, {failed} erreurs. Scores bruts : {SCORES_PATH}")

        if not scores:
            return
        labels = convert_all(scores)
        print("\nRépartition des niveaux obtenus :")
        print_distribution(labels)

        # mesure sur les jeux de référence (mêmes mesures que evaluate_labelling)
        rows = []
        if os.path.exists(args.reference):
            reference, skipped = load_reference(args.reference)
            by_name = {}
            for name in labels:
                by_name[normalize(name)] = name
            for ref_name, expected in reference.items():
                found = by_name.get(normalize(ref_name))
                if found is None:
                    continue
                rows.append(
                    {
                        "game": ref_name,
                        "expected": expected,
                        "predicted": labels[found],
                        "seconds": games[found][1],
                    }
                )
        if rows:
            metrics = compute_metrics(rows)
            print(f"\nMesuré sur {len(rows)} jeux de ta référence :")
            print(f"  Exactitude          : {metrics['accuracy']:.0%}")
            print(f"  À un cran près      : {metrics['within1']:.0%}")
            print(f"  Écart moyen en crans: {metrics['mean_abs_step_error']:.2f}")
            print(f"  Indice d'effondrement: {metrics['collapse_index']:.0%}")
            for key in KEYS:
                print(f"    {key:11} exact {metrics['acc_' + key]:.0%}  ±1 {metrics['within1_' + key]:.0%}")
            if not args.no_mlflow and not args.limit:
                args.method = "scores"
                args.reasoning = False
                log_to_mlflow(args, "scores-" + str(len(PROPORTIONS)), metrics, rows, len(rows))

        if args.write:
            for name in labels:
                save_labels(engine, games[name][0], labels[name])
            print(f"\n{len(labels)} jeux écrits en base.")
        else:
            print("\nRien écrit en base (ajoute --write pour enregistrer ces niveaux).")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()