"""Entraîne la SVD sur les notes de Users_Games et suit les essais dans MLflow.

On met 20 % des notes de côté (jeu de test), on entraîne sur les 80 % restants et on mesure
l'erreur (RMSE) sur les notes cachées. On essaie plusieurs nombres de facteurs, on garde le
meilleur, puis on réentraîne sur toutes les notes et on sauvegarde le modèle.
Pour comparer, on calcule aussi une base très simple : prédire la moyenne de l'utilisateur.

Usage (depuis la racine du projet, serveur MLflow lancé) :
    python -m ml.svd.train
"""
import math
import random

import mlflow
from sqlalchemy import create_engine, text

from config.settings import get_settings
from ml.svd.model import SvdModel

SEED = 42
PART_TEST = 0.2
FACTEURS_A_ESSAYER = [2, 3, 5, 8]
CHEMIN_MODELE = get_settings().SVD_MODEL_PATH


def charger_notes(conn):
    lignes = conn.execute(
        text("SELECT user_id, game_id, rating FROM Users_Games WHERE rating IS NOT NULL")
    ).fetchall()
    notes = []
    for ligne in lignes:
        notes.append((ligne.user_id, ligne.game_id, ligne.rating))
    return notes


def separer(notes, part_test, seed):
    melange = list(notes)
    random.Random(seed).shuffle(melange)
    nb_test = int(len(melange) * part_test)
    return melange[nb_test:], melange[:nb_test]


def rmse(model, notes):
    somme = 0.0
    for user_id, game_id, note in notes:
        ecart = model.predict(user_id, game_id) - note
        somme += ecart * ecart
    return math.sqrt(somme / len(notes))


def rmse_base(entrainement, test):
    # Base de comparaison : on prédit toujours la moyenne de l'utilisateur
    modele_vide = SvdModel(nb_facteurs=1).fit(entrainement)
    modele_vide.facteurs_user = modele_vide.facteurs_user * 0
    return rmse(modele_vide, test)


def main():
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        notes = charger_notes(conn)
    print(len(notes), "notes chargées")

    entrainement, test = separer(notes, PART_TEST, SEED)
    base = rmse_base(entrainement, test)
    print("Base (moyenne de l'utilisateur) : RMSE", round(base, 3))

    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
    mlflow.set_experiment("svd-recommandation")

    meilleur_k = None
    meilleur_rmse = None
    for k in FACTEURS_A_ESSAYER:
        with mlflow.start_run(run_name="essai_k" + str(k)):
            modele = SvdModel(nb_facteurs=k).fit(entrainement)
            erreur = rmse(modele, test)
            mlflow.log_param("nb_facteurs", k)
            mlflow.log_param("part_test", PART_TEST)
            mlflow.log_param("seed", SEED)
            mlflow.log_metric("rmse_test", erreur)
            mlflow.log_metric("rmse_base_moyenne_user", base)
            print("k =", k, ": RMSE", round(erreur, 3))
        if meilleur_rmse is None or erreur < meilleur_rmse:
            meilleur_rmse = erreur
            meilleur_k = k

    with mlflow.start_run(run_name="modele_final_k" + str(meilleur_k)):
        final = SvdModel(nb_facteurs=meilleur_k).fit(notes)
        final.save(CHEMIN_MODELE)
        mlflow.log_param("nb_facteurs", meilleur_k)
        mlflow.log_param("nb_notes", len(notes))
        mlflow.log_metric("rmse_test_du_meilleur_essai", meilleur_rmse)
        mlflow.log_artifact(CHEMIN_MODELE)
    print("Meilleur k :", meilleur_k, "- modèle sauvegardé dans", CHEMIN_MODELE)


if __name__ == "__main__":
    main()
