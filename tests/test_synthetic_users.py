from ingestion.generate_synthetic_users import affinite, note_depuis_affinite

FAN_DE_PLATFORM = {"styles": ["Platform"], "difficulte": 4, "hasard": 1}


def test_un_jeu_qui_correspond_plait_plus_qu_un_jeu_qui_ne_correspond_pas():
    jeu_ideal = {"styles": ["Platform"], "difficulte": 4, "hasard": 1}
    jeu_oppose = {"styles": ["Sport"], "difficulte": 1, "hasard": 5}
    assert affinite(FAN_DE_PLATFORM, jeu_ideal) > affinite(FAN_DE_PLATFORM, jeu_oppose)
