from ingestion.ingest_steam import is_same_game


def test_meme_jeu_ou_edition_est_accepte():
    assert is_same_game("Age of Empires II", "Age of Empires II: Definitive Edition")
    assert is_same_game("Assassin's Creed II", "Assassin's Creed 2")


def test_suite_ou_autre_jeu_est_refuse():
    assert not is_same_game("Portal", "Portal 2")
    assert not is_same_game("Kingdom Hearts", "KINGDOM HEARTS IV")
    assert not is_same_game("StarCraft", "Star Crafter")
