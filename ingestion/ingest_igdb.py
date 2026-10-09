"""Enrich Games from IGDB and write straight into MySQL (same connection as ingest_speedrun.py).

For each game that has no style yet, look it up on IGDB (exact name, then full-text search).
Names are compared ignoring case, accents, punctuation and word order.
  - "exact":     the name matches
                 -> fills the genres (Styles / Style_Games) and game_dimension
                    (side view -> 2D; first person, third person, VR -> 3D; only if unambiguous.
                    Isometric / bird view is NOT mapped: it mixes 2D and 3D games.)
  - "platform":  no match, but it matches once a platform tag like "(DS)" or "(GBC)" is removed
                 -> genres only (the dimension can differ between ports)
  - "fuzzy" / "not_found": nothing is written; listed in data/igdb_review.json for manual review.
  - "accepted":  only with --accept-fuzzy: the best IGDB hit of a "fuzzy" game is trusted and
                 written like an "exact" one. Use it ONLY after checking data/igdb_review.json.

game_length is not filled here: it comes from the speedrun.com world records
(ingest_speedrun_times.py).

Usage (from the project root):
    python -m ingestion.ingest_igdb --limit 20     # test on 20 games
    python -m ingestion.ingest_igdb                # every game without styles yet (resumable)
    python -m ingestion.ingest_igdb --accept-fuzzy # after you checked the review file by hand

Env vars (or .env): IGDB_CLIENT_ID, IGDB_CLIENT_SECRET   (Twitch app credentials)
The database comes from get_settings().DATABASE_URL.
"""
import argparse
import json
import os
import time
import unicodedata

import requests
from config.settings import get_settings
from sqlalchemy import create_engine, text

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
GAMES_URL = "https://api.igdb.com/v4/games"
FIELDS = "name,genres.name,player_perspectives.name,total_rating_count"
MIN_DELAY = 0.3  # IGDB limit is 4 requests/second
REVIEW_PATH = "data/igdb_review.json"

# IGDB has no 2D/3D field: this is a heuristic on player perspectives.
# A dimension is written only if every mapped perspective gives the same value.
# "Bird view / Isometric" is left out on purpose: it covers top-down 2D games as well as 3D ones.
# Empty this dict to leave game_dimension untouched.
PERSPECTIVE_TO_DIMENSION = {
    "Side view": "2D",
    "First person": "3D",
    "Third person": "3D",
    "Virtual Reality": "3D",
}

# Trailing "(tag)" in speedrun.com names that is removed on a second attempt.
# Only these tags are removed: "(2023)" or "(Remake)" must stay, they change the game.
# Values are compared after normalize(): lowercase, no punctuation.
PLATFORM_TAGS = [
    "ds", "3ds", "gb", "gbc", "gba", "nes", "snes", "n64", "gc", "gcn", "wii", "wii u",
    "switch", "psp", "vita", "ps1", "psx", "ps2", "ps3", "ps4", "ps5", "pc", "xbox",
    "x360", "genesis", "mega drive", "sms", "gg", "saturn", "dreamcast", "dc",
    "arcade", "mobile", "ios", "android",
]


def normalize(s: str) -> str:
    """Lowercase, strip accents and punctuation, collapse spaces."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    cleaned = ""
    for c in s:
        if c.isalnum():
            cleaned += c
        else:
            cleaned += " "
    return " ".join(cleaned.split())


def same_name(a: str, b: str) -> bool:
    """Same name ignoring case, accents, punctuation and word order."""
    na = normalize(a)
    nb = normalize(b)
    if na == nb:
        return True
    return sorted(na.split()) == sorted(nb.split())


def strip_platform_tag(name: str) -> str | None:
    """'Dragon Quest IV (DS)' -> 'Dragon Quest IV'. None if there is no known platform tag."""
    stripped = name.strip()
    if not stripped.endswith(")"):
        return None
    pos = stripped.rfind("(")
    if pos <= 0:
        return None
    tag = normalize(stripped[pos + 1 : -1])
    if tag not in PLATFORM_TAGS:
        return None
    return stripped[:pos].strip()


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} est vide ou absent du .env (voir https://dev.twitch.tv/console/apps).")
    return value


def get_token() -> str:
    resp = requests.post(
        TOKEN_URL,
        params={
            "client_id": require_env("IGDB_CLIENT_ID"),
            "client_secret": require_env("IGDB_CLIENT_SECRET"),
            "grant_type": "client_credentials",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def query(token: str, url: str, body: str) -> list[dict]:
    headers = {
        "Client-ID": os.environ["IGDB_CLIENT_ID"],
        "Authorization": f"Bearer {token}",
    }
    for attempt in range(3):
        time.sleep(MIN_DELAY)
        # The body must be sent as UTF-8 bytes: a plain str is encoded as latin-1 by the HTTP
        # library, and IGDB answers 400 Bad Request to names with accents ("Pokémon").
        resp = requests.post(url, headers=headers, data=body.encode("utf-8"), timeout=15)
        if resp.status_code == 429:  # rate limited -> wait and retry
            time.sleep(1 + attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("IGDB rate limit: 3 retries failed")


def best(results: list[dict]) -> dict:
    """Most popular entry (IGDB rating count) as tie-breaker."""
    return max(results, key=lambda r: r.get("total_rating_count", 0))


def search_name(token: str, name: str) -> tuple[str, dict | None]:
    """Look for one name on IGDB: 'exact', 'fuzzy' (best hit, not trusted) or 'not_found'."""
    safe = name.replace("\\", "\\\\").replace('"', '\\"')
    # 1) exact name, then 2) full-text search
    bodies = (
        f'fields {FIELDS}; where name = "{safe}"; limit 5;',
        f'search "{safe}"; fields {FIELDS}; limit 10;',
    )
    last_results: list[dict] = []
    for body in bodies:
        results = query(token, GAMES_URL, body)
        last_results = results or last_results
        exact = []
        for r in results:
            if same_name(r["name"], name):
                exact.append(r)
        if exact:
            return "exact", best(exact)
    if last_results:
        return "fuzzy", best(last_results)
    return "not_found", None


def find_game(token: str, name: str) -> tuple[str, dict | None]:
    """'exact', 'platform' (matched without its platform tag), 'fuzzy' or 'not_found'."""
    status, game = search_name(token, name)
    if status == "exact":
        return status, game
    base = strip_platform_tag(name)
    if base:
        base_status, base_game = search_name(token, base)
        if base_status == "exact":
            return "platform", base_game
    return status, game


def guess_dimension(game: dict) -> str | None:
    found = []
    for p in game.get("player_perspectives", []):
        dim = PERSPECTIVE_TO_DIMENSION.get(p["name"])
        if dim is not None and dim not in found:
            found.append(dim)
    if len(found) == 1:
        return found[0]
    return None


def genre_names(game: dict) -> list[str]:
    names = []
    for g in game.get("genres", []):
        names.append(g["name"][:50])  # Styles.style_name is VARCHAR(50)
    return names


def get_pending_games(engine, limit: int | None) -> list:
    """Games that have no style yet (= not enriched yet)."""
    sql = (
        "SELECT g.id, g.game_name FROM Games g "
        "LEFT JOIN Style_Games sg ON sg.game_id = g.id "
        "WHERE sg.game_id IS NULL ORDER BY g.id"
    )
    params = {}
    if limit:
        sql += " LIMIT :limit"
        params = {"limit": limit}
    with engine.connect() as conn:
        result = conn.execute(text(sql), params)
        return list(result.fetchall())


def save_game(engine, game_id: int, game: dict, with_details: bool) -> None:
    """Genres always; game_dimension only when with_details is True."""
    # engine.begin(): one transaction per game, commit on success, rollback on error
    with engine.begin() as conn:
        if with_details:
            dimension = guess_dimension(game)
            if dimension is not None:
                conn.execute(
                    text("UPDATE Games SET game_dimension = :dim WHERE id = :id"),
                    {"dim": dimension, "id": game_id},
                )
        for style_name in genre_names(game):
            conn.execute(
                text("INSERT IGNORE INTO Styles (style_name) VALUES (:name)"),
                {"name": style_name},
            )
            row = conn.execute(
                text("SELECT id FROM Styles WHERE style_name = :name"),
                {"name": style_name},
            ).fetchone()
            conn.execute(
                text("INSERT IGNORE INTO Style_Games (game_id, style_id) VALUES (:game, :style)"),
                {"game": game_id, "style": row[0]},
            )


def write_review(review: list[dict]) -> None:
    os.makedirs("data", exist_ok=True)
    with open(REVIEW_PATH, "w", encoding="utf-8") as f:
        json.dump(review, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="max games to process")
    parser.add_argument(
        "--accept-fuzzy",
        action="store_true",
        help="write the best IGDB hit of fuzzy games (only after checking the review file)",
    )
    args = parser.parse_args()

    engine = create_engine(get_settings().DATABASE_URL)
    try:
        pending = get_pending_games(engine, args.limit)
        print(f"{len(pending)} games to enrich")
        if not pending:
            return

        token = get_token()
        review = []
        counts: dict[str, int] = {}
        try:
            for i, row in enumerate(pending, 1):
                game_id, name = row
                name = name.strip()
                try:
                    status, game = find_game(token, name)
                    if status == "fuzzy" and args.accept_fuzzy:
                        status = "accepted"  # trusted on purpose, see --accept-fuzzy
                    if status in ("exact", "accepted"):
                        save_game(engine, game_id, game, True)
                    elif status == "platform":
                        save_game(engine, game_id, game, False)
                except Exception as exc:  # network/API/DB error: skip, retried on next run
                    print(f"[{i}/{len(pending)}] ERROR {name}: {exc}")
                    continue
                counts[status] = counts.get(status, 0) + 1
                candidate = None
                if game is not None:
                    candidate = game["name"]
                if status not in ("exact", "platform", "accepted"):
                    review.append(
                        {
                            "game_id": game_id,
                            "game_name": name,
                            "status": status,
                            "igdb_candidate": candidate,
                        }
                    )
                line = f"[{i}/{len(pending)}] {status:9} {name}"
                if candidate:
                    line += f"  ->  {candidate}"
                print(line)
        finally:
            write_review(review)
        print("Summary:", counts)
        print(f"fuzzy / not_found (not written to the DB) listed in {REVIEW_PATH}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()