"""Score the local labelling model against YOUR labels and log the run in MLflow.

You write the expected labels of ~20 games you know well in data/labels_reference.json.
This script runs the model on exactly those games (nothing is written to the database), compares its
answers with yours, prints the result and records one MLflow run, so models / prompts / settings can
be compared side by side.

Metrics (all between 0 and 1 except the last two):
  accuracy              share of labels identical to yours (the 4 keys together)
  within1               share of labels at most ONE step away from yours (e.g. avance vs difficile)
  acc_<key>, within1_<key>   the same, for each of the 4 keys
  collapse_index        how often the model's most frequent word comes back (1 = always the same word)
  invalid_rate          share of games where the model gave no valid answer
  mean_abs_step_error   average distance in steps between its labels and yours
  avg_seconds           average time per game

Usage (from the project root, Ollama running):
    pip install mlflow
    mlflow ui --port 5000                                  # in ANOTHER terminal, from the project root
    python -m ingestion.evaluate_labelling                              # default model
    python -m ingestion.evaluate_labelling --reasoning
    python -m ingestion.evaluate_labelling --model gemma3:12b --reasoning
    python -m ingestion.evaluate_labelling --no-mlflow                  # console only

Then open http://localhost:5000 and compare the runs of the experiment "labelling".
The MLflow address comes from MLFLOW_TRACKING_URI (default http://localhost:5000).
"""
import argparse
import hashlib
import json
import os
import time

from config.settings import get_settings
from sqlalchemy import create_engine

from ingestion.ingest_igdb import normalize
from ingestion.label_games_local import (
    DEFAULT_CATEGORY,
    DEFAULT_MODEL,
    SCALE_A,
    SCALE_B,
    ask_model,
    build_prompt,
    check_ollama,
    get_pending_games,
    load_categories,
    make_schema,
    validate,
)

REFERENCE_PATH = "data/labels_reference.json"
EXPERIMENT = "labelling"
KEYS = ["difficulty", "execution", "randomness", "glitchness"]


def scale_for(key: str) -> list:
    if key in ("difficulty", "execution"):
        return SCALE_A
    return SCALE_B


def load_reference(path: str) -> tuple[dict, list]:
    """(games with 4 valid labels, names of the incomplete / invalid ones). Keys starting with _ are notes."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    reference = {}
    skipped = []
    for name, labels in data.items():
        if name.startswith("_"):
            continue
        clean = {}
        valid = isinstance(labels, dict)
        if valid:
            for key in KEYS:
                value = labels.get(key, "")
                if isinstance(value, str):
                    value = normalize(value)
                else:
                    value = ""
                if value not in scale_for(key):
                    valid = False
                    break
                clean[key] = value
        if valid:
            reference[name] = clean
        else:
            skipped.append(name)
    return reference, skipped


def compute_metrics(rows: list) -> dict:
    """rows: [{"expected": {...}, "predicted": {...} or None, "seconds": float}, ...]"""
    total = len(rows)
    valid = []
    seconds_sum = 0.0
    for row in rows:
        seconds_sum += row["seconds"]
        if row["predicted"] is not None:
            valid.append(row)

    metrics = {"n_games": total, "n_valid": len(valid)}
    if total == 0:
        return metrics
    metrics["invalid_rate"] = (total - len(valid)) / total
    metrics["avg_seconds"] = seconds_sum / total
    if not valid:
        return metrics

    exact_total = 0
    within_total = 0
    step_total = 0
    share_total = 0.0
    n = len(valid)
    for key in KEYS:
        scale = scale_for(key)
        exact = 0
        within = 0
        counts = {}
        for row in valid:
            expected_index = scale.index(row["expected"][key])
            predicted_index = scale.index(row["predicted"][key])
            distance = abs(expected_index - predicted_index)
            if distance == 0:
                exact += 1
            if distance <= 1:
                within += 1
            step_total += distance
            word = row["predicted"][key]
            counts[word] = counts.get(word, 0) + 1
        top_share = max(counts.values()) / n
        metrics[f"acc_{key}"] = exact / n
        metrics[f"within1_{key}"] = within / n
        metrics[f"top_label_share_{key}"] = top_share
        exact_total += exact
        within_total += within
        share_total += top_share

    n_labels = n * len(KEYS)
    metrics["accuracy"] = exact_total / n_labels
    metrics["within1"] = within_total / n_labels
    metrics["mean_abs_step_error"] = step_total / n_labels
    metrics["collapse_index"] = share_total / len(KEYS)
    return metrics


def prompt_fingerprint(with_reasoning: bool) -> str:
    """Short hash of the prompt template: it changes automatically whenever the prompt is edited."""
    template = build_prompt("{game}", ["{categories}"], "{genres}", "{dimension}", 1, with_reasoning)
    return hashlib.sha1(template.encode("utf-8")).hexdigest()[:8]


def file_fingerprint(path: str) -> str:
    """Short hash of the reference file: it changes as soon as one of your labels changes."""
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:8]


def log_to_mlflow(args, fingerprint: str, metrics: dict, rows: list, n_reference: int) -> None:
    # fail fast if the MLflow server is not running (the default is a long series of retries)
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "1")
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "10")
    try:
        import mlflow
    except ImportError:
        print("mlflow n'est pas installé (pip install mlflow) : résultats affichés seulement.")
        return
    method = getattr(args, "method", "labels")
    run_name = args.model
    if args.reasoning:
        run_name += " + reasoning"
    if method != "labels":
        run_name += f" ({method})"
    try:
        mlflow.set_tracking_uri(get_settings().MLFLOW_TRACKING_URI)
        mlflow.set_experiment(EXPERIMENT)
        with mlflow.start_run(run_name=run_name):
            mlflow.log_params(
                {
                    "model": args.model,
                    "reasoning": args.reasoning,
                    "method": method,
                    "prompt_hash": fingerprint,
                    "reference_hash": file_fingerprint(args.reference),
                    "temperature": 0,
                    "n_reference_games": n_reference,
                }
            )
            mlflow.log_metrics(metrics)
            mlflow.log_dict({"games": rows}, "predictions.json")
            mlflow.log_artifact(args.reference)  # the exact reference used for this run
        print(f"Run enregistré dans MLflow : expérience '{EXPERIMENT}', run '{run_name}'.")
    except Exception as exc:
        print(f"MLflow inaccessible ({exc}). Lance `mlflow ui --port 5000` dans un autre terminal. Résultats non enregistrés.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default {DEFAULT_MODEL})")
    parser.add_argument("--reasoning", action="store_true", help="the model writes a short reasoning first")
    parser.add_argument("--reference", default=REFERENCE_PATH, help="file with your expected labels")
    parser.add_argument("--no-mlflow", action="store_true", help="do not record the run in MLflow")
    args = parser.parse_args()

    if not os.path.exists(args.reference):
        print(f"{args.reference} introuvable. Copie le modèle labels_reference.json dans data/ et remplis-le.")
        return
    reference, skipped = load_reference(args.reference)
    print(f"{len(reference)} jeux de référence complets.")
    if skipped:
        print(f"{len(skipped)} jeux ignorés (labels vides ou invalides) : {', '.join(skipped)}")
    if not reference:
        print("Aucun jeu complet : remplis au moins quelques jeux dans le fichier de référence.")
        return
    if not check_ollama(args.model):
        return

    reference_by_key = {}
    for name, labels in reference.items():
        reference_by_key[normalize(name)] = (name, labels)

    engine = create_engine(get_settings().DATABASE_URL)
    rows = []
    try:
        games = get_pending_games(engine, None, True, list(reference.keys()))
        found = set()
        categories = load_categories()
        schema = make_schema(args.reasoning)
        for i, game in enumerate(games, 1):
            game_id, db_name, dimension, length, genres = game
            db_name = db_name.strip()
            entry = reference_by_key.get(normalize(db_name))
            if entry is None:
                continue
            name, expected = entry
            found.add(name)
            game_categories = categories.get(normalize(db_name), [DEFAULT_CATEGORY])
            prompt = build_prompt(db_name, game_categories, genres, dimension, length, args.reasoning)
            predicted = None
            reasoning = None
            started = time.time()
            try:
                answer = ask_model(args.model, prompt, schema)
                reasoning = answer.get("reasoning")
                predicted = validate(answer)
            except Exception as exc:
                print(f"   ERREUR {db_name}: {exc}")
            seconds = time.time() - started

            row = {"game": name, "expected": expected, "predicted": predicted, "seconds": round(seconds, 2)}
            if reasoning:
                row["reasoning"] = reasoning
            rows.append(row)

            if predicted is None:
                print(f"[{i}/{len(games)}] {name}: réponse invalide")
            else:
                parts = []
                for key in KEYS:
                    mark = "ok" if expected[key] == predicted[key] else "!!"
                    parts.append(f"{key[:4]} {expected[key]}>{predicted[key]} {mark}")
                print(f"[{i}/{len(games)}] {name}: " + " | ".join(parts))

        for name in reference:
            if name not in found:
                print(f"Absent de la base, ignoré : {name}")
    finally:
        engine.dispose()

    metrics = compute_metrics(rows)
    print()
    if "accuracy" in metrics:
        print(f"Exactitude (identique à toi)   : {metrics['accuracy']:.0%}")
        print(f"À un cran près                 : {metrics['within1']:.0%}")
        print(f"Écart moyen en crans           : {metrics['mean_abs_step_error']:.2f}")
        print(f"Indice d'effondrement          : {metrics['collapse_index']:.0%}  (100% = toujours le même mot)")
        for key in KEYS:
            print(f"  {key:11} exact {metrics['acc_' + key]:.0%}  ±1 {metrics['within1_' + key]:.0%}")
    print(f"Réponses invalides : {metrics.get('invalid_rate', 0):.0%} | temps moyen : {metrics.get('avg_seconds', 0):.1f} s/jeu")

    if not args.no_mlflow and rows:
        log_to_mlflow(args, prompt_fingerprint(args.reasoning), metrics, rows, len(reference))


if __name__ == "__main__":
    main()