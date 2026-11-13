"""Construit le prompt d'explication d'une recommandation (partie "RAG").

On donne au modèle : les infos du jeu, les goûts du joueur et quelques extraits de textes du jeu
retrouvés dans ChromaDB. On lui demande de n'utiliser QUE ces informations.
"""


def decrire_liste(valeurs):
    if len(valeurs) == 0:
        return "non précisé"
    return ", ".join(valeurs)


def construire_prompt(jeu, preferences, extraits):
    # jeu : {"nom", "styles", "difficulte", "hasard"} ; preferences : {"styles", "difficulte", "hasard"}
    lignes = []
    lignes.append("Tu expliques à un joueur de speedrun pourquoi un jeu lui est recommandé.")
    lignes.append("")
    lignes.append("Jeu : " + jeu["nom"])
    lignes.append("Styles du jeu : " + decrire_liste(jeu["styles"]))
    lignes.append("Difficulté du jeu : " + (jeu["difficulte"] or "non précisée"))
    lignes.append("Part de hasard du jeu : " + (jeu["hasard"] or "non précisée"))
    lignes.append("")
    lignes.append("Goûts du joueur")
    lignes.append("Styles aimés : " + decrire_liste(preferences["styles"]))
    lignes.append("Difficulté préférée : " + (preferences["difficulte"] or "non précisée"))
    lignes.append("Part de hasard préférée : " + (preferences["hasard"] or "non précisée"))
    lignes.append("")
    lignes.append("Extraits de textes sur le jeu (en anglais) :")
    if len(extraits) == 0:
        lignes.append("(aucun extrait disponible)")
    for extrait in extraits:
        lignes.append("- " + extrait)
    lignes.append("")
    lignes.append(
        "Explique en français, en 3 phrases maximum, pourquoi ce jeu peut plaire à ce joueur. "
        "Les styles, la difficulté et le hasard du jeu sont UNIQUEMENT ceux écrits dans la partie Jeu : "
        "ne les confonds jamais avec les goûts du joueur. "
        "Utilise uniquement les informations ci-dessus et n'invente rien. "
        "S'il n'y a aucun extrait, ne décris pas le jeu au-delà de la partie Jeu et dis que les textes manquent."
    )
    return "\n".join(lignes)
