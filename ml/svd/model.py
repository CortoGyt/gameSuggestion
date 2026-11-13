"""Modèle de recommandation par SVD (décomposition en valeurs singulières), avec numpy seul.

Principe :
1. On range les notes dans une grande table : une ligne par utilisateur, une colonne par jeu.
2. On retire à chaque note la moyenne de son utilisateur (certains notent plus généreusement).
3. Les notes manquantes valent 0 (= "dans la moyenne de l'utilisateur").
4. La SVD résume la table en quelques "facteurs" (des goûts cachés). On n'en garde que k.
5. Note prédite = moyenne de l'utilisateur + (ses facteurs x les facteurs du jeu), bornée de 1 à 5.
"""
import pickle

import numpy as np


class SvdModel:
    def __init__(self, nb_facteurs=5):
        self.nb_facteurs = nb_facteurs
        self.moyenne_globale = 3.0
        self.indice_user = {}
        self.indice_game = {}
        self.moyenne_user = {}
        self.facteurs_user = None
        self.facteurs_game = None
        self.jeux_notes = {}  # user_id -> ensemble des game_id déjà notés

    def fit(self, notes):
        # notes : liste de tuples (user_id, game_id, note)
        somme = 0
        for user_id, game_id, note in notes:
            somme += note
            if user_id not in self.indice_user:
                self.indice_user[user_id] = len(self.indice_user)
            if game_id not in self.indice_game:
                self.indice_game[game_id] = len(self.indice_game)
        self.moyenne_globale = somme / len(notes)

        nb_users = len(self.indice_user)
        nb_games = len(self.indice_game)
        table = np.zeros((nb_users, nb_games))
        connu = np.zeros((nb_users, nb_games), dtype=bool)
        total_user = np.zeros(nb_users)
        nombre_user = np.zeros(nb_users)
        for user_id, game_id, note in notes:
            i = self.indice_user[user_id]
            j = self.indice_game[game_id]
            table[i, j] = note
            connu[i, j] = True
            total_user[i] += note
            nombre_user[i] += 1
            if user_id not in self.jeux_notes:
                self.jeux_notes[user_id] = set()
            self.jeux_notes[user_id].add(game_id)

        moyennes = total_user / nombre_user
        for user_id, i in self.indice_user.items():
            self.moyenne_user[user_id] = float(moyennes[i])

        centree = np.zeros((nb_users, nb_games))
        for i in range(nb_users):
            for j in range(nb_games):
                if connu[i, j]:
                    centree[i, j] = table[i, j] - moyennes[i]

        u, s, vt = np.linalg.svd(centree, full_matrices=False)
        k = min(self.nb_facteurs, len(s))
        self.facteurs_user = u[:, :k] * s[:k]
        self.facteurs_game = vt[:k, :].T
        return self

    def predict(self, user_id, game_id):
        if user_id not in self.indice_user:
            return self.moyenne_globale
        base = self.moyenne_user[user_id]
        if game_id not in self.indice_game:
            return base
        i = self.indice_user[user_id]
        j = self.indice_game[game_id]
        note = base + float(np.dot(self.facteurs_user[i], self.facteurs_game[j]))
        if note < 1.0:
            return 1.0
        if note > 5.0:
            return 5.0
        return note

    def recommend(self, user_id, n=10):
        # Les n jeux non notés avec la meilleure note prédite. Utilisateur inconnu : liste vide.
        if user_id not in self.indice_user:
            return []
        resultats = []
        for game_id in self.indice_game:
            if game_id in self.jeux_notes[user_id]:
                continue
            resultats.append((game_id, self.predict(user_id, game_id)))
        resultats.sort(key=lambda couple: couple[1], reverse=True)
        return resultats[:n]

    def save(self, chemin):
        with open(chemin, "wb") as fichier:
            pickle.dump(self, fichier)

    @staticmethod
    def load(chemin):
        with open(chemin, "rb") as fichier:
            return pickle.load(fichier)
