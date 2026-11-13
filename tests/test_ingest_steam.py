from ingestion.ingest_steam import is_same_game, pick_best_match


def test_meme_jeu_ou_edition_est_accepte():
    assert is_same_game("Age of Empires II", "Age of Empires II: Definitive Edition")
    assert is_same_game("Assassin's Creed II", "Assassin's Creed 2")


def test_suite_ou_autre_jeu_est_refuse():
    assert not is_same_game("Portal", "Portal 2")
    assert not is_same_game("Kingdom Hearts", "KINGDOM HEARTS IV")
    assert not is_same_game("StarCraft", "Star Crafter")


def test_titre_exact_passe_avant_une_edition():
    resultats_steam = [
        {"id": 2, "name": "Celeste Remastered", "type": "app"},
        {"id": 504230, "name": "Celeste", "type": "app"},
    ]
    assert pick_best_match("Celeste", resultats_steam) == (504230, "Celeste")
