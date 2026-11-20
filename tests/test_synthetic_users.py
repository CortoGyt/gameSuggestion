from ingestion.generate_synthetic_users import affinite, note_depuis_affinite

FAN_DE_PLATFORM = {"styles": ["Platform"], "difficulte": "haut", "hasard": "bas"}


def test_un_jeu_qui_correspond_plait_plus_qu_un_jeu_qui_ne_correspond_pas():
    jeu_ideal = {"styles": ["Platform"], "difficulte": "haut", "hasard": "bas"}
    jeu_oppose = {"styles": ["Sport"], "difficulte": "bas", "hasard": "haut"}
    assert affinite(FAN_DE_PLATFORM, jeu_ideal) > affinite(FAN_DE_PLATFORM, jeu_oppose)
