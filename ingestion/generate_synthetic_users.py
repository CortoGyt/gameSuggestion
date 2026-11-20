"""Génère 10 utilisateurs fictifs et leurs notes dans Users et Users_Games.

Ces données sont SYNTHÉTIQUES : elles servent à entraîner et tester la SVD tant qu'il n'y a
pas de vrais utilisateurs. Chaque utilisateur est un archétype (styles préférés, difficulté
et part de hasard qu'il aime). Sa note pour un jeu vient de la ressemblance entre ses goûts
et les labels du jeu, plus un peu de bruit. Le tirage est fixé par une graine : relancer le
script redonne exactement les mêmes notes.

Les comptes s'appellent synth_<archétype>. Leur mot de passe est invalide : ils ne peuvent pas
se connecter. Relancer le script efface d'abord les anciens comptes synth_ puis les recrée.

Usage (depuis la racine du projet) :
    python -m ingestion.generate_synthetic_users
"""
import random

from sqlalchemy import create_engine, text

from config.settings import get_settings

SEED = 42
NB_NOTES_PAR_UTILISATEUR = 100
BRUIT_MAX = 0.7  # le bruit décale la note de -0,7 à +0,7 point (avant arrondi)
MOT_DE_PASSE_INVALIDE = "!synthetic"

# styles : genres IGDB aimés (liste vide = pas de préférence de genre)
# difficulte, hasard : niveau préféré, "bas", "moyen" ou "haut"
ARCHETYPES = [
    {"nom": "platformer_precis", "styles": ["Platform", "Indie"], "difficulte": "haut", "hasard": "bas"},
    {"nom": "fan_de_rpg", "styles": ["Role-playing (RPG)", "Adventure"], "difficulte": "moyen", "hasard": "moyen"},
    {"nom": "fan_de_tir", "styles": ["Shooter"], "difficulte": "moyen", "hasard": "bas"},
    {
        "nom": "stratege",
        "styles": ["Strategy", "Real Time Strategy (RTS)", "Turn-based strategy (TBS)"],
        "difficulte": "moyen",
        "hasard": "moyen",
    },
    {"nom": "amateur_de_puzzle", "styles": ["Puzzle", "Point-and-click", "Adventure"], "difficulte": "bas", "hasard": "bas"},
    {"nom": "retro_arcade", "styles": ["Arcade", "Platform", "Fighting"], "difficulte": "moyen", "hasard": "bas"},
    {"nom": "fan_de_hasard", "styles": ["Indie", "Hack and slash/Beat 'em up"], "difficulte": "haut", "hasard": "haut"},
    {"nom": "explorateur_tranquille", "styles": ["Adventure", "Simulator", "Puzzle"], "difficulte": "bas", "hasard": "bas"},
    {"nom": "challenger_hardcore", "styles": [], "difficulte": "haut", "hasard": "moyen"},
    {"nom": "course_et_sport", "styles": ["Racing", "Sport", "Arcade"], "difficulte": "bas", "hasard": "moyen"},
]


# Rang de chaque niveau, pour pouvoir mesurer l'écart entre deux niveaux
RANG = {"bas": 0, "moyen": 1, "haut": 2}


def proximite(valeur_jeu, valeur_preferee):
    # 1 si le jeu est exactement au niveau préféré, 0 si l'écart est maximal (2 crans)
    if valeur_jeu is None:
        return 0.5  # label absent : ni pour ni contre
    return 1 - abs(RANG[valeur_jeu] - RANG[valeur_preferee]) / 2


def affinite(utilisateur, jeu):
    # Ressemblance entre les goûts de l'utilisateur et un jeu, de 0 à 1
    if len(utilisateur["styles"]) == 0:
        score_style = 0.5
    else:
        score_style = 0.0
        for style in jeu["styles"]:
            if style in utilisateur["styles"]:
                score_style = 1.0
    score_difficulte = proximite(jeu["difficulte"], utilisateur["difficulte"])
    score_hasard = proximite(jeu["hasard"], utilisateur["hasard"])
    return 0.5 * score_style + 0.3 * score_difficulte + 0.2 * score_hasard


def note_depuis_affinite(valeur_affinite, bruit):
    # Affinité 0..1 -> note 1..5, bruit compris, toujours bornée
    note = round(1 + 4 * valeur_affinite + bruit)
    if note < 1:
        return 1
    if note > 5:
        return 5
    return note


def charger_jeux(conn):
    lignes = conn.execute(
        text("SELECT id, difficulty, randomness FROM Games ORDER BY id")
    ).fetchall()
    jeux = {}
    for ligne in lignes:
        jeux[ligne.id] = {"id": ligne.id, "difficulte": ligne.difficulty, "hasard": ligne.randomness, "styles": []}
    styles = conn.execute(
        text("SELECT sg.game_id, s.style_name FROM Style_Games sg JOIN Styles s ON s.id = sg.style_id")
    ).fetchall()
    for ligne in styles:
        jeux[ligne.game_id]["styles"].append(ligne.style_name)
    return list(jeux.values())


def supprimer_anciens_comptes(conn):
    conn.execute(text("DELETE FROM Users_Games WHERE user_id IN (SELECT id FROM Users WHERE user_name LIKE 'synth%')"))
    conn.execute(text("DELETE FROM Users WHERE user_name LIKE 'synth%'"))


def creer_utilisateur(conn, nom):
    conn.execute(
        text(
            "INSERT INTO Users (user_name, user_pw_hash, role_id) "
            "VALUES (:nom, :hash, (SELECT id FROM Roles WHERE name = 'user'))"
        ),
        {"nom": "synth_" + nom, "hash": MOT_DE_PASSE_INVALIDE},
    )
    return conn.execute(text("SELECT id FROM Users WHERE user_name = :nom"), {"nom": "synth_" + nom}).scalar()


def main():
    hasard = random.Random(SEED)
    engine = create_engine(get_settings().DATABASE_URL)

    with engine.begin() as conn:
        jeux = charger_jeux(conn)
        supprimer_anciens_comptes(conn)

        total_par_note = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for utilisateur in ARCHETYPES:
            user_id = creer_utilisateur(conn, utilisateur["nom"])
            jeux_notes = hasard.sample(jeux, NB_NOTES_PAR_UTILISATEUR)
            somme = 0
            for jeu in jeux_notes:
                bruit = hasard.uniform(-BRUIT_MAX, BRUIT_MAX)
                note = note_depuis_affinite(affinite(utilisateur, jeu), bruit)
                conn.execute(
                    text(
                        "INSERT INTO Users_Games (user_id, game_id, rating, source) "
                        "VALUES (:u, :g, :r, 'interaction')"
                    ),
                    {"u": user_id, "g": jeu["id"], "r": note},
                )
                total_par_note[note] += 1
                somme += note
            moyenne = round(somme / NB_NOTES_PAR_UTILISATEUR, 2)
            print("  synth_" + utilisateur["nom"] + " : " + str(NB_NOTES_PAR_UTILISATEUR) + " notes, moyenne " + str(moyenne))

    print("Répartition des notes (1 à 5) :", total_par_note)
    engine.dispose()


if __name__ == "__main__":
    main()
