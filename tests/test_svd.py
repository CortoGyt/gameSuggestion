from ml.svd.model import SvdModel

# 3 utilisateurs, 4 jeux : u1 et u2 aiment les jeux 1-2, u3 aime les jeux 3-4
NOTES = [
    (1, 1, 5), (1, 2, 5), (1, 3, 1),
    (2, 1, 4), (2, 2, 5), (2, 4, 2),
    (3, 3, 5), (3, 4, 5), (3, 1, 1),
]


def test_les_notes_predites_restent_entre_1_et_5():
    modele = SvdModel(nb_facteurs=2).fit(NOTES)
    for user_id in [1, 2, 3]:
        for game_id in [1, 2, 3, 4]:
            assert 1.0 <= modele.predict(user_id, game_id) <= 5.0


def test_on_ne_recommande_pas_un_jeu_deja_note():
    modele = SvdModel(nb_facteurs=2).fit(NOTES)
    recommandes = modele.recommend(1, n=10)
    ids = []
    for game_id, note in recommandes:
        ids.append(game_id)
    assert ids == [4]
