from ml.vector.chromadb_vector import chunk_text


def test_decoupage_en_morceaux_courts():
    # Une ligne = un morceau ; une ligne trop longue est coupée avant la limite
    morceaux = chunk_text("premier avis\n\nsecond avis\n" + "mot " * 400, max_chars=100)
    assert morceaux[0] == "premier avis"
    assert morceaux[1] == "second avis"
    for morceau in morceaux:
        assert len(morceau) <= 100
