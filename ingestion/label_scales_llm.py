import json
import time
import unicodedata
from config.settings import get_settings
from groq import Groq
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Récupère les paramètres de configuration
settings = get_settings()

# Crée le moteur SQLAlchemy
engine = create_engine(settings.DATABASE_URL)
Session = sessionmaker(bind=engine)

# Listes autorisées pour chaque échelle
DIFFICULT_ECHELLE_DE_VALEURS = ["facile", "intermediaire", "avance", "difficile", "extreme"]
RANDOMNESS_GLITCHNESS_VALEURS = ["aucun", "bas", "moyen", "haut", "extreme"]


def charger_donnees_speedrun():
    """Charge les données speedrun.com depuis le JSON."""
    with open("data/speedrun_raw.json", encoding="utf-8") as f:
        donnees = json.load(f)
    return donnees


def recuperer_jeux_labellises(session):
    """Récupère la liste des jeux déjà labellisés."""
    requete = text("SELECT game_name FROM Games WHERE difficulty_id IS NOT NULL")
    resultats = session.execute(requete)
    jeux_labellises = set()
    for ligne in resultats:
        jeux_labellises.add(ligne[0])
    return jeux_labellises


def recuperer_id_echelle(session, label, table_echelle):
    """Récupère l'ID d'une valeur dans la table d'échelle."""
    requete = text(f"SELECT id FROM {table_echelle} WHERE label = :label")
    resultat = session.execute(requete, {"label": label})
    ligne = resultat.fetchone()
    if ligne:
        return ligne[0]
    return None


def construire_prompt(nom_jeu, categories):
    """Construit le prompt pour l'appel LLM."""
    categories_texte = ", ".join(categories)
    prompt = f"""You are a video game expert. Analyze the game "{nom_jeu}" with its speedrun categories: {categories_texte}

Respond ONLY with valid JSON containing exactly these 4 keys (no other text):
Give exactly ONE overall assessment for the whole game, even if multiple categories are listed below. Do not return one assessment per category — return a single flat JSON object.

SCALE A (use ONLY for difficulty and execution): facile, intermediaire, avance, difficile, extreme
SCALE B (use ONLY for randomness and glitchness): aucun, bas, moyen, haut, extreme

The 4 keys to fill:
- "difficulty": one word from SCALE A
- "execution": one word from SCALE A
- "randomness": one word from SCALE B
- "glitchness": one word from SCALE B

NEVER use a SCALE B word for difficulty or execution. NEVER use a SCALE A word for randomness or glitchness.
Keep the French words exactly as written above, even though these instructions are in English. Do not translate them to English.

IMPORTANT: use EXACTLY one of the words listed above for each key. Do not translate, paraphrase, abbreviate, or invent a new word.

Example of valid response:
{{"difficulty": "avance", "execution": "difficile", "randomness": "moyen", "glitchness": "bas"}}

Analysis for: {nom_jeu}
Categories: {categories_texte}"""
    return prompt


def valider_reponse(reponse_dict):
    """Valide que la réponse contient les bonnes clés et valeurs."""
    cles_requises = ["difficulty", "execution", "randomness", "glitchness"]

    for cle in cles_requises:
        if cle not in reponse_dict:
            return False

    for cle in ["difficulty", "execution"]:
        valeur_normalisee = normaliser(reponse_dict[cle])
        if valeur_normalisee not in DIFFICULT_ECHELLE_DE_VALEURS:
            return False
        reponse_dict[cle] = valeur_normalisee

    for cle in ["randomness", "glitchness"]:
        valeur_normalisee = normaliser(reponse_dict[cle])
        if valeur_normalisee not in RANDOMNESS_GLITCHNESS_VALEURS:
            return False
        reponse_dict[cle] = valeur_normalisee

    return True


def appeler_llm(client, nom_jeu, categories):
    """Appelle le modèle LLM pour obtenir les labels."""
    prompt = construire_prompt(nom_jeu, categories)

    try:
        reponse = client.chat.completions.create(
            model=settings.GROQ_LABELLING_MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            response_format={"type": "json_object"}
        )

        # Extrait le contenu du message
        if reponse and reponse.choices and len(reponse.choices) > 0:
            contenu = reponse.choices[0].message.content
            reponse_dict = json.loads(contenu)
            return reponse_dict
        return None
    except Exception as e:
        print(f"   Erreur appel LLM: {str(e)}")
        return None


def mettre_a_jour_jeu(session, nom_jeu, labels_dict):
    """Met à jour la ligne du jeu avec les IDs des échelles."""
    # Récupère les IDs des labels
    difficulty_id = recuperer_id_echelle(session, labels_dict["difficulty"], "EchellesDE")
    execution_id = recuperer_id_echelle(session, labels_dict["execution"], "EchellesDE")
    randomness_id = recuperer_id_echelle(session, labels_dict["randomness"], "EchellesRG")
    glitchness_id = recuperer_id_echelle(session, labels_dict["glitchness"], "EchellesRG")

    if not all([difficulty_id, execution_id, randomness_id, glitchness_id]):
        return False

    # Met à jour la ligne
    requete = text("""
        UPDATE Games 
        SET difficulty_id = :difficulty_id,
            execution_id = :execution_id,
            randomness_id = :randomness_id,
            glitchness_id = :glitchness_id
        WHERE game_name = :game_name
    """)

    session.execute(requete, {
        "difficulty_id": difficulty_id,
        "execution_id": execution_id,
        "randomness_id": randomness_id,
        "glitchness_id": glitchness_id,
        "game_name": nom_jeu
    })
    session.commit()
    return True

def normaliser(valeur):
    """Enlève accents et met en minuscule."""
    return unicodedata.normalize('NFKD', valeur).encode('ascii', 'ignore').decode('ascii').lower()

def main():
    """Fonction principale."""
    print("Chargement des données")
    donnees_speedrun = charger_donnees_speedrun()

    session = Session()

    print("Récupération des jeux déjà labellisés...")
    jeux_labellises = recuperer_jeux_labellises(session)
    print(f"   {len(jeux_labellises)} jeux déjà traités")

    # Filtrer les jeux à traiter
    jeux_a_traiter = []
    for entree in donnees_speedrun:
        nom_jeu = entree.get("game_name")
        if nom_jeu and nom_jeu not in jeux_labellises:
            jeux_a_traiter.append(entree)

    print(f"{len(jeux_a_traiter)} jeux à labelliser")

    # Initialise le client LLM
    client = Groq(api_key=settings.GROQ_API_KEY)

    # Compteurs
    reussis = 0
    echoues = 0
    jeux_echoues = []

    # Traite chaque jeu
    index_courant = 1
    for entree in jeux_a_traiter:
        nom_jeu = entree.get("game_name")
        categories = entree.get("categories", [])

        print(f"\n[{index_courant}/{len(jeux_a_traiter)}] Traitement: {nom_jeu}")

        # Appel LLM
        labels_dict = appeler_llm(client, nom_jeu, categories)

        if labels_dict is None:
            print("  Échec: pas de réponse LLM")
            echoues = echoues + 1
            jeux_echoues.append(nom_jeu)
            index_courant = index_courant + 1
            time.sleep(2.1)
            continue

        # Validation
        if not valider_reponse(labels_dict):
            print("  Échec: réponse invalide")
            print(f"     Reçu: {labels_dict}")
            echoues = echoues + 1
            jeux_echoues.append(nom_jeu)
            index_courant = index_courant + 1
            time.sleep(1)
            continue

        # Mise à jour
        try:
            succes = mettre_a_jour_jeu(session, nom_jeu, labels_dict)
            if succes:
                print("  Succès")
                print(f"     Difficulté: {labels_dict['difficulty']}, Exécution: {labels_dict['execution']}")
                print(f"     Hasard: {labels_dict['randomness']}, Glitches: {labels_dict['glitchness']}")
                reussis = reussis + 1
            else:
                print("  Échec: IDs d'échelle non trouvés")
                echoues = echoues + 1
                jeux_echoues.append(nom_jeu)
        except Exception as e:
            print(f"  Échec mise à jour DB: {str(e)}")
            echoues = echoues + 1
            jeux_echoues.append(nom_jeu)

        index_courant = index_courant + 1
        time.sleep(1)

    session.close()

    # Affichage des résultats
    print("\n" + "="*60)
    print("RÉSULTATS DE L'EXÉCUTION")
    print("="*60)
    print(f"Jeux labellisés avec succès: {reussis}")
    print(f"Jeux en échec: {echoues}")

    if jeux_echoues:
        print("\nJeux en échec:")
        for nom_jeu in jeux_echoues:
            print(f"   - {nom_jeu}")

    # Requête de confirmation
    session_confirmation = Session()
    requete_confirmation = text("SELECT COUNT(*) FROM Games WHERE difficulty_id IS NOT NULL")
    resultat = session_confirmation.execute(requete_confirmation)
    total_labellises = resultat.scalar()
    session_confirmation.close()

    print(f"\nTotal cumulé de jeux labellisés: {total_labellises}")
    print("="*60)


if __name__ == "__main__":
    main()
