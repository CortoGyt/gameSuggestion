from ingestion.generate_synthetic_users import affinite, note_depuis_affinite

FAN_DE_PLATFORM = {"styles": ["Platform"], "difficulte": 4, "hasard": 1}


def test_un_jeu_qui_correspond_plait_plus_qu_un_jeu_qui_ne_correspond_pas():
    jeu_ideal = {"styles": ["Platform"], "difficulte": 4, "hasard": 1}
    jeu_oppose = {"styles": ["Sport"], "difficulte": 1, "hasard": 5}
    assert affinite(FAN_DE_PLATFORM, jeu_ideal) > affinite(FAN_DE_PLATFORM, jeu_oppose)


def test_la_note_reste_entre_1_et_5():
    assert note_depuis_affinite(0.0, -0.7) == 1
    assert note_depuis_affinite(1.0, 0.7) == 5
