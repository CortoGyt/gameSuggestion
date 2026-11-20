"""Mesure l'étiquetage du modèle local en le comparant à TES labels, et enregistre le run dans MLflow.

Ce fichier fournit les outils utilisés par label_games_scores.py :
- load_reference : lit tes labels attendus (data/labels_reference.json) ;
- compute_metrics : compare les réponses du modèle aux tiennes ;
- log_to_mlflow : enregistre un run dans MLflow pour comparer modèles et prompts côte à côte.

Mesures (entre 0 et 1, sauf les deux dernières) :
  accuracy              part des labels identiques aux tiens (les 4 critères ensemble)
  within1               part des labels à un cran au plus des tiens (par exemple bas contre moyen)
  acc_<critère>, within1_<critère>   la même chose, pour chacun des 4 critères
  collapse_index        à quelle fréquence le mot le plus fréquent revient (1 = toujours le même mot)
  invalid_rate          part des jeux où le modèle n'a donné aucune réponse valable
  mean_abs_step_error   distance moyenne en crans entre ses labels et les tiens
  avg_seconds           temps moyen par jeu

Pour comparer les runs : lance `mlflow ui --port 5000` dans un autre terminal, depuis la racine du projet,
puis ouvre http://localhost:5000 et regarde l'expérience « labelling ».
L'adresse MLflow vient de MLFLOW_TRACKING_URI (par défaut http://localhost:5000).
"""
import hashlib
import json
import os

from config.settings import get_settings

from ingestion.ingest_igdb import normalize
from ingestion.label_games_local import LEVELS

REFERENCE_PATH = "data/labels_reference.json"
EXPERIMENT = "labelling"
KEYS = ["difficulty", "execution", "randomness", "glitchness"]


def scale_for(key: str) -> list:
    # Les 4 critères utilisent la même échelle à 3 niveaux
    return LEVELS


def load_reference(path: str) -> tuple[dict, list]:
    """(jeux avec 4 labels valides, noms des jeux incomplets ou invalides). Les clés qui commencent par _ sont des notes."""
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
    """rows : [{"expected": {...}, "predicted": {...} ou None, "seconds": nombre}, ...]"""
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


def file_fingerprint(path: str) -> str:
    """Empreinte courte du fichier de référence : elle change dès qu'un de tes labels change."""
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:8]


def log_to_mlflow(args, fingerprint: str, metrics: dict, rows: list, n_reference: int) -> None:
    # échoue vite si le serveur MLflow ne tourne pas (par défaut il réessaie très longtemps)
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
            mlflow.log_artifact(args.reference)  # la référence exacte utilisée pour ce run
        print(f"Run enregistré dans MLflow : expérience '{EXPERIMENT}', run '{run_name}'.")
    except Exception as exc:
        print(f"MLflow inaccessible ({exc}). Lance `mlflow ui --port 5000` dans un autre terminal. Résultats non enregistrés.")
