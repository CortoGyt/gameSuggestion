from sqlalchemy import create_engine, text

from ingestion.ingest_igdb_texts import games_without_text


def test_jeux_sans_texte_ignore_ceux_qui_en_ont_deja():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE Games (id INTEGER PRIMARY KEY, game_name TEXT)"))
        conn.execute(text("CREATE TABLE Textes (game_id INT, source TEXT, content TEXT)"))
        conn.execute(text("INSERT INTO Games VALUES (1, 'Celeste'), (2, 'Zelda'), (3, 'Metroid')"))
        # Celeste a un texte Steam, Metroid un résumé IGDB : seul Zelda n'a rien
        conn.execute(text("INSERT INTO Textes VALUES (1, 'steam_blurb', 'x'), (3, 'igdb_summary', 'y')"))
        jeux = games_without_text(conn, 0)
    assert len(jeux) == 1
    assert jeux[0].game_name == "Zelda"
