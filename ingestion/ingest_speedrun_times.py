"""Fill Games.game_length with the world-record time (in minutes) of the main category, from speedrun.com.

For each game that has no game_length yet:
  1. search the game on speedrun.com by name; the match is trusted only if the name is the same
     (ignoring case, accents, punctuation and word order)
  2. read its full-game leaderboards (miscellaneous categories excluded), top 1 run of each
  3. main category = "Any%" if it has a timed run, otherwise the first category that has one
  4. game_length = the world-record time of that category, rounded to minutes
Games with no match, or with no timed run (score-based or empty leaderboards), stay NULL.
Fuzzy / not found games are listed in data/speedrun_times_review.json.

Usage (from the project root):
    python -m ingestion.ingest_speedrun_times --limit 10      # test on 10 games
    python -m ingestion.ingest_speedrun_times                 # every game without game_length
    python -m ingestion.ingest_speedrun_times --accept-fuzzy  # after checking the review file by hand

The database comes from get_settings().DATABASE_URL. No API key needed.
"""
import argparse
import json
import os
import time

import requests
from config.settings import get_settings
from sqlalchemy import create_engine, text

from ingestion.ingest_igdb import normalize, same_name

BASE_URL = "https://www.speedrun.com/api/v1"
HEADERS = {"User-Agent": "gamesuggestion-school-project/1.0"}
MIN_DELAY = 1.5  # pause before each request (records)
SEARCH_DELAY = 4.0  # the name search (/games?name=...) is limited much harder than the rest (Cloudflare 429)
MAX_RETRIES = 5
MAX_WAIT = 300  # seconds, cap for a single pause after a 429
MAX_CONSECUTIVE_ERRORS = 5  # stop the run if the API keeps failing
REVIEW_PATH = "data/speedrun_times_review.json"
MAIN_CATEGORY = "any"  # normalize("Any%")


def api_get(path: str, params: dict):
    delay = MIN_DELAY
    if path == "/games":
        delay = SEARCH_DELAY
    for attempt in range(MAX_RETRIES):
        time.sleep(delay)
        resp = requests.get(f"{BASE_URL}{path}", params=params, headers=HEADERS, timeout=15)
        if resp.status_code == 429:  # rate limited -> pause (server's Retry-After if given), then retry
            wait = 30 * (attempt + 1)
            retry_after = resp.headers.get("Retry-After", "")
            if retry_after.isdigit():
                wait = int(retry_after) + 2
            wait = min(wait, MAX_WAIT)
            print(f"   rate limit speedrun.com, pause {wait}s (essai {attempt + 1}/{MAX_RETRIES})")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()["data"]
    raise RuntimeError(f"speedrun.com rate limit: {MAX_RETRIES} retries failed")


def find_game(name: str) -> tuple[str, dict | None]:
    """'exact', 'fuzzy' (best search hit, not trusted) or 'not_found'."""
    results = api_get("/games", {"name": name, "max": 20})
    for game in results:  # results are sorted by similarity: the first exact one is the best
        if same_name(game["names"]["international"], name):
            return "exact", game
    if results:
        return "fuzzy", results[0]
    return "not_found", None


def category_name(board: dict) -> str:
    """Name of the leaderboard's category (needs embed=category), '' if not embedded."""
    category = board.get("category")
    if isinstance(category, dict):
        return category.get("data", {}).get("name", "")
    return ""


def pick_main_time(boards: list[dict]) -> tuple[str, int] | None:
    """(category name, world record in minutes) of the main category, None if no timed run."""
    candidates = []
    for board in boards:
        runs = board.get("runs", [])
        if not runs:
            continue
        seconds = runs[0]["run"]["times"].get("primary_t")
        if not seconds or seconds <= 0:  # score-based leaderboard: no usable time
            continue
        candidates.append((category_name(board), seconds))
    if not candidates:
        return None
    chosen = candidates[0]
    for candidate in candidates:
        if normalize(candidate[0]) == MAIN_CATEGORY:
            chosen = candidate
            break
    return chosen[0], max(1, round(chosen[1] / 60))


def get_main_time(game_id: str) -> tuple[str, int] | None:
    boards = api_get(
        f"/games/{game_id}/records",
        {
            "top": 1,
            "scope": "full-game",
            "miscellaneous": "no",
            "skip-empty": "yes",
            "embed": "category",
        },
    )
    return pick_main_time(boards)


def get_pending_games(engine, limit: int | None) -> list:
    sql = "SELECT id, game_name FROM Games WHERE game_length IS NULL ORDER BY id"
    params = {}
    if limit:
        sql += " LIMIT :limit"
        params = {"limit": limit}
    with engine.connect() as conn:
        return list(conn.execute(text(sql), params).fetchall())


def save_length(engine, game_id: int, minutes: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE Games SET game_length = :length WHERE id = :id"),
            {"length": minutes, "id": game_id},
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
        help="trust the best speedrun.com hit of fuzzy games (only after checking the review file)",
    )
    args = parser.parse_args()

    engine = create_engine(get_settings().DATABASE_URL)
    try:
        pending = get_pending_games(engine, args.limit)
        print(f"{len(pending)} games without game_length")
        review = []
        counts: dict[str, int] = {}
        consecutive_errors = 0
        try:
            for i, row in enumerate(pending, 1):
                game_id, name = row
                name = name.strip()
                detail = ""
                try:
                    status, game = find_game(name)
                    if status == "fuzzy" and args.accept_fuzzy:
                        status = "accepted"
                    if status in ("exact", "accepted"):
                        result = get_main_time(game["id"])
                        if result is None:
                            status = "no_time"
                        else:
                            save_length(engine, game_id, result[1])
                            detail = f"  =>  {result[0]}: {result[1]} min"
                except Exception as exc:  # network/API/DB error: skip, retried on next run
                    print(f"[{i}/{len(pending)}] ERROR {name}: {exc}")
                    consecutive_errors += 1
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        print(f"{MAX_CONSECUTIVE_ERRORS} erreurs de suite : arrêt. Attends 2-3 minutes puis relance la même commande.")
                        break
                    continue
                consecutive_errors = 0
                counts[status] = counts.get(status, 0) + 1
                candidate = None
                if game is not None:
                    candidate = game["names"]["international"]
                if status in ("fuzzy", "not_found"):
                    review.append(
                        {
                            "game_id": game_id,
                            "game_name": name,
                            "status": status,
                            "speedrun_candidate": candidate,
                        }
                    )
                line = f"[{i}/{len(pending)}] {status:9} {name}"
                if candidate and status != "exact":
                    line += f"  ->  {candidate}"
                print(line + detail)
        finally:
            write_review(review)
        print("Summary:", counts)
        print(f"fuzzy / not_found listed in {REVIEW_PATH}; no_time = matched but no timed run (stays NULL)")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
