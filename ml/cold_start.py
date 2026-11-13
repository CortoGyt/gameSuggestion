"""Démarrage à froid : recommander à un utilisateur qui n'a encore noté aucun jeu.

On compare ses préférences (styles aimés, difficulté, part de hasard) aux labels de chaque jeu.
Score de 0 à 1 : 50 % le style, 30 % la difficulté, 20 % le hasard.
"""


def proximite(valeur_jeu, valeur_preferee):
    # 1 si le jeu est exactement au niveau préféré, 0 si l'écart est maximal (4 niveaux)
    if valeur_jeu is None or valeur_preferee is None:
        return 0.5  # information absente : ni pour ni contre
    return 1 - abs(valeur_jeu - valeur_preferee) / 4


def score_jeu(preferences, jeu):
    if len(preferences["styles"]) == 0:
        score_style = 0.5
    else:
        score_style = 0.0
        for style in jeu["styles"]:
            if style in preferences["styles"]:
                score_style = 1.0
    score_difficulte = proximite(jeu["difficulte"], preferences["difficulte"])
    score_hasard = proximite(jeu["hasard"], preferences["hasard"])
    return 0.5 * score_style + 0.3 * score_difficulte + 0.2 * score_hasard


def classer_jeux(preferences, jeux, n):
    # Les n jeux qui ressemblent le plus aux préférences : liste de (jeu, score)
    classement = []
    for jeu in jeux:
        classement.append((jeu, score_jeu(preferences, jeu)))
    classement.sort(key=lambda couple: couple[1], reverse=True)
    return classement[:n]
