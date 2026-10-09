import os

import requests
import streamlit as st

# Adresse de l'API (modifiable par variable d'environnement)
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
PAGE_SIZE = 20

st.set_page_config(page_title="Game Suggestion", layout="wide")


@st.cache_data(ttl=60)
def fetch_games(q, page):
    # Appelle GET /games ; renvoie (données, message d'erreur)
    params = {"limit": PAGE_SIZE, "offset": (page - 1) * PAGE_SIZE}
    if q:
        params["q"] = q
    try:
        response = requests.get(API_BASE_URL + "/games", params=params, timeout=5)
        response.raise_for_status()
        return response.json(), None
    except requests.RequestException:
        return None, "L'API est injoignable. Vérifie qu'elle tourne (uvicorn main:app)."


def games_to_rows(games):
    rows = []
    for game in games:
        rows.append(
            {
                "Jeu": game["name"],
                "Durée (min)": game["length_minutes"],
                "Dimension": game["dimension"],
                "Difficulté": game["difficulty"],
                "Exécution": game["execution"],
                "Aléatoire": game["randomness"],
                "Glitchs": game["glitchness"],
                "Styles": ", ".join(game["styles"]),
            }
        )
    return rows


def page_home():
    st.subheader("Bienvenue !")
    st.write("Parcours le catalogue de jeux de speedrun dans l'onglet Catalogue.")


def page_catalogue():
    st.subheader("Catalogue")
    q = st.text_input("Rechercher un jeu")
    page = st.number_input("Page", min_value=1, value=1, step=1)

    data, error = fetch_games(q, int(page))
    if error:
        st.error(error)
        return

    st.caption(str(data["total"]) + " jeu(x) trouvé(s)")
    if len(data["items"]) == 0:
        st.info("Aucun jeu à afficher pour cette page.")
        return
    st.dataframe(games_to_rows(data["items"]), hide_index=True)


st.title("GameSuggestion")
st.markdown("Découvre tes prochains jeux préférés")

with st.sidebar:
    st.header("Navigation")
    page_name = st.radio("Aller à", ["Accueil", "Catalogue"])

if page_name == "Accueil":
    page_home()
else:
    page_catalogue()