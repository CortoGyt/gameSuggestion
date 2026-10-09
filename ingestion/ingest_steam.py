"""Récupère pour chaque jeu un texte descriptif et des avis Steam, et les range dans la table Textes.

Sources (publiques, sans clé d'API) :
    - store.steampowered.com/api/storesearch  : retrouve l'appid d'un jeu à partir de son nom
    - store.steampowered.com/api/appdetails   : description courte  -> Textes.source = 'steam_blurb'
    - store.steampowered.com/appreviews/<id>  : avis les plus utiles -> Textes.source = 'steam_reviews'

Le script reprend là où il s'est arrêté : un jeu qui a déjà ses deux textes est sauté.
Les jeux introuvables sur Steam sont listés dans data/steam_unmatched.txt.

Usage (depuis la racine du projet) :
    python -m ingestion.ingest_steam --limit 5      # test sur 5 jeux
    python -m ingestion.ingest_steam                # tous les jeux
"""
import argparse
import html
import json
import re
import time
from pathlib import Path

import requests
from sqlalchemy import create_engine, text

from config.settings import get_settings

SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
DETAILS_URL = "https://store.steampowered.com/api/appdetails"
REVIEWS_URL = "https://store.steampowered.com/appreviews/"

NB_REVIEWS = 10
MAX_REVIEW_CHARS = 600
PAUSE_SECONDS = 1.5  # Steam limite les appels répétés

DATA_DIR = Path("data")
APPIDS_FILE = DATA_DIR / "steam_appids.json"
UNMATCHED_FILE = DATA_DIR / "steam_unmatched.txt"


# ---------- Fonctions pures (testées sans réseau) ----------

ROMAN_TO_DIGIT = {
    "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6",
    "vii": "7", "viii": "8", "ix": "9", "x": "10",
}

# Mots qui désignent une édition du MÊME jeu (jamais une suite ni un spin-off)
EDITION_PHRASES = ["game of the year", "the final cut", "directors cut", "director s cut"]
EDITION_WORDS = [
    "the", "definitive", "edition", "remastered", "remaster", "remake", "goty", "special",
    "enhanced", "anniversary", "complete", "deluxe", "hd", "resurrected", "infernal",
    "dx", "gold", "ultimate", "redux", "classic", "royal", "treasure", "trove",
]


def normalize_name(name):
    # minuscules, sans ponctuation ni symboles (™, ®...), pour comparer deux titres
    name = name.lower()
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    return " ".join(name.split())


def canonical_name(name):
    # Forme de comparaison: chiffres romains -> arabes, mots d'édition retirés
    text_value = " " + normalize_name(name) + " "
    for phrase in EDITION_PHRASES:
        text_value = text_value.replace(" " + phrase + " ", " ")
    tokens = []
    for token in text_value.split():
        if token in EDITION_WORDS:
            continue
        tokens.append(ROMAN_TO_DIGIT.get(token, token))
    return " ".join(tokens)


def is_same_game(game_name, steam_name):
    return canonical_name(game_name) == canonical_name(steam_name)


def pick_best_match(game_name, items):
    # items : liste de résultats de storesearch. Renvoie (appid, nom Steam) ou None.
    # Un titre identique l'emporte sur une simple édition ; sinon "introuvable".
    edition_match = None
    for item in items:
        if item.get("type") != "app":
            continue
        steam_name = item.get("name", "")
        if normalize_name(steam_name) == normalize_name(game_name):
            return item["id"], steam_name
        if edition_match is None and is_same_game(game_name, steam_name):
            edition_match = (item["id"], steam_name)
    return edition_match


def clean_html(raw):
    no_tags = re.sub(r"<[^>]+>", " ", raw or "")
    return " ".join(html.unescape(no_tags).split())


def strip_bbcode(raw):
    # Retire les balises de mise en forme Steam : [b], [/b], [quote=Nom], [url=...], [h1]...
    return re.sub(r"\[/?\w+(?:=[^\]]*)?\]", " ", raw)


def build_reviews_text(reviews):
    # Concatène les avis (tronqués) en un seul texte, un avis par ligne
    lines = []
    for review in reviews[:NB_REVIEWS]:
        content = strip_bbcode(review.get("review") or "")
        content = " ".join(content.split())
        if len(content) < 40:
            continue
        lines.append(content[:MAX_REVIEW_CHARS])
    return "\n".join(lines)


# ---------- Réseau ----------

def get_json(url, params):
    # 3 essais ; en cas de limitation (429), on attend plus longtemps
    for attempt in range(3):
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 429:
                time.sleep(30 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            time.sleep(3)
    return None


def find_appid(game_name):
    data = get_json(SEARCH_URL, {"term": game_name, "cc": "us", "l": "english"})
    if not data:
        return None
    return pick_best_match(game_name, data.get("items", []))


def fetch_blurb(appid):
    data = get_json(DETAILS_URL, {"appids": appid, "l": "english"})
    if not data or not data.get(str(appid), {}).get("success"):
        return ""
    return clean_html(data[str(appid)]["data"].get("short_description"))


def fetch_reviews_text(appid):
    data = get_json(
        REVIEWS_URL + str(appid),
        {"json": 1, "language": "english", "filter": "all", "num_per_page": 30, "purchase_type": "all"},
    )
    if not data:
        return ""
    return build_reviews_text(data.get("reviews", []))


# ---------- Base de données ----------

def games_to_process(conn, limit):
    # Jeux auxquels il manque au moins un des deux textes
    query = """
        SELECT g.id, g.game_name,
               SUM(t.source = 'steam_blurb') AS has_blurb,
               SUM(t.source = 'steam_reviews') AS has_reviews
        FROM Games g LEFT JOIN Textes t ON t.game_id = g.id
        GROUP BY g.id, g.game_name
        HAVING COALESCE(SUM(t.source = 'steam_blurb'), 0) = 0
            OR COALESCE(SUM(t.source = 'steam_reviews'), 0) = 0
        ORDER BY g.game_name
    """
    rows = conn.execute(text(query)).fetchall()
    if limit:
        rows = rows[:limit]
    return rows


def insert_text(conn, game_id, source, content):
    conn.execute(
        text("INSERT INTO Textes (game_id, source, content) VALUES (:g, :s, :c)"),
        {"g": game_id, "s": source, "c": content},
    )


def load_json(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def main():
    parser = argparse.ArgumentParser(description="Ingestion des textes Steam dans la table Textes")
    parser.add_argument("--limit", type=int, default=0, help="Nombre maximum de jeux à traiter (0 = tous)")
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    appids = load_json(APPIDS_FILE)
    unmatched = []
    engine = create_engine(get_settings().DATABASE_URL)

    with engine.begin() as conn:
        games = games_to_process(conn, args.limit)
    print(str(len(games)) + " jeu(x) à traiter")

    for game in games:
        game_id = game.id
        name = game.game_name

        if name in appids:
            appid = appids[name]["appid"]
        else:
            match = find_appid(name)
            time.sleep(PAUSE_SECONDS)
            if match is None:
                print("  [introuvable] " + name)
                unmatched.append(name)
                continue
            appid = match[0]
            appids[name] = {"appid": appid, "steam_name": match[1]}

        added = []
        with engine.begin() as conn:
            if not game.has_blurb:
                blurb = fetch_blurb(appid)
                time.sleep(PAUSE_SECONDS)
                if blurb:
                    insert_text(conn, game_id, "steam_blurb", blurb)
                    added.append("blurb")
            if not game.has_reviews:
                reviews = fetch_reviews_text(appid)
                time.sleep(PAUSE_SECONDS)
                if reviews:
                    insert_text(conn, game_id, "steam_reviews", reviews)
                    added.append("avis")

        print("  " + name + " -> " + appids[name]["steam_name"] + " (" + ", ".join(added) + ")")
        APPIDS_FILE.write_text(json.dumps(appids, indent=2, ensure_ascii=False), encoding="utf-8")

    if unmatched:
        UNMATCHED_FILE.write_text("\n".join(unmatched), encoding="utf-8")
        print(str(len(unmatched)) + " jeu(x) introuvable(s), voir " + str(UNMATCHED_FILE))


if __name__ == "__main__":
    main()