
import frontend.streamlit as st

st.set_page_config(page_title="Game Suggestion", layout="wide")

st.title("GameSuggestion")
st.markdown("Découvre tes prochains jeux préférés")

# Sidebar
with st.sidebar:
    st.header("Navigation")
    page = st.radio("Aller à", ["Home", "Recommendations", "Profile", "Admin"])

if page == "Home":
    st.subheader("Bienvenue!")
    # À compléter

elif page == "Recommendations":
    st.subheader("Mes Recommandations")
    # À compléter
