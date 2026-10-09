from sqlalchemy import create_engine, text

from ingestion.ingest_igdb_texts import build_igdb_text, games_without_text


def test_build_text_joins_summary_and_storyline():
    game = {"summary": "A  platformer\nwith plumbers.", "storyline": "Save the princess."}
    assert build_igdb_text(game) == "A platformer with plumbers.\n\nSave the princess."


def test_build_text_handles_missing_fields():
    assert build_igdb_text({"summary": "Only a summary."}) == "Only a summary."
    assert build_igdb_text({}) == ""


def test_games_without_text_skips_games_that_already_have_one():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE Games (id INTEGER PRIMARY KEY, game_name TEXT)"))
        conn.execute(text("CREATE TABLE Textes (game_id INT, source TEXT, content TEXT)"))
        conn.execute(text("INSERT INTO Games VALUES (1, 'Celeste'), (2, 'Zelda'), (3, 'Metroid')"))
        conn.execute(text("INSERT INTO Textes VALUES (1, 'steam_blurb', 'x'), (3, 'igdb_summary', 'y')"))
        rows = games_without_text(conn, 0)
    assert len(rows) == 1
    assert rows[0].game_name == "Zelda"