from ingestion.ingest_steam import (
    build_reviews_text,
    canonical_name,
    clean_html,
    is_same_game,
    normalize_name,
    pick_best_match,
    strip_bbcode,
)


def test_normalize_name_removes_symbols_and_case():
    assert normalize_name("Hollow Knight™: Edition!") == "hollow knight edition"


def test_roman_numerals_match_digits():
    assert is_same_game("Assassin's Creed II", "Assassin's Creed 2")
    assert is_same_game("Dark Souls II", "DARK SOULS™ II")


def test_editions_of_the_same_game_match():
    assert is_same_game("Age of Empires II", "Age of Empires II: Definitive Edition")
    assert is_same_game("Dark Souls", "DARK SOULS™: REMASTERED")
    assert is_same_game("Sekiro: Shadows Die Twice", "Sekiro™: Shadows Die Twice - GOTY Edition")
    assert is_same_game("Serious Sam HD: The First Encounter", "Serious Sam: The First Encounter")
    assert is_same_game("Disco Elysium", "Disco Elysium - The Final Cut")


def test_sequels_and_spinoffs_do_not_match():
    wrong = [
        ("Kingdom Hearts", "KINGDOM HEARTS IV"),
        ("Final Fantasy X", "FINAL FANTASY XVI"),
        ("StarCraft", "Star Crafter"),
        ("Castlevania", "Castlevania: Belmont's Curse"),
        ("Minecraft", "Minecraft Dungeons II"),
        ("Max Payne", "Max Payne 3"),
        ("Life is Strange", "Life is Strange 2"),
        ("Portal", "Portal 2"),
        ("Pac-Man", "PAC-MAN WORLD 2 Re-PAC"),
        ("Call of Duty 4: Modern Warfare", "Call of Duty®: Modern Warfare® 4"),
    ]
    for game, steam in wrong:
        assert not is_same_game(game, steam), game


def test_pick_best_match_prefers_exact_title():
    items = [
        {"id": 1, "name": "Celeste Soundtrack", "type": "dlc"},
        {"id": 2, "name": "Celeste Remastered", "type": "app"},
        {"id": 504230, "name": "Celeste", "type": "app"},
    ]
    assert pick_best_match("Celeste", items) == (504230, "Celeste")


def test_pick_best_match_accepts_edition_when_no_exact():
    items = [{"id": 813780, "name": "Age of Empires II: Definitive Edition", "type": "app"}]
    assert pick_best_match("Age of Empires II", items) == (813780, "Age of Empires II: Definitive Edition")


def test_pick_best_match_rejects_other_games_and_empty():
    items = [{"id": 7, "name": "Totally Different Game", "type": "app"}]
    assert pick_best_match("Celeste", items) is None
    assert pick_best_match("Celeste", []) is None


def test_canonical_name_is_stable():
    assert canonical_name("The Witcher 3: Wild Hunt — Remastered") == canonical_name("Witcher 3 Wild Hunt")


def test_clean_html_strips_tags_and_entities():
    assert clean_html("<b>Hello</b> &amp; <i>bye</i>") == "Hello & bye"
    assert clean_html(None) == ""


def test_build_reviews_text_skips_short_and_truncates():
    reviews = [
        {"review": "too short"},
        {"review": "x" * 2000},
        {"review": "A really good platformer with tight controls and great music."},
    ]
    lines = build_reviews_text(reviews).split("\n")
    assert len(lines) == 2
    assert len(lines[0]) == 600


def test_strip_bbcode_removes_steam_tags():
    raw = '[quote=Ezio] "It is a good life." [/quote] [h1]Great[/h1] [b]game[/b]'
    cleaned = " ".join(strip_bbcode(raw).split())
    assert cleaned == '"It is a good life." Great game'