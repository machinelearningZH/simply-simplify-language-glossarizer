import streamlit as st

from_text = st.Page("from_text.py", title="von Text", icon=":material/description:")
from_url = st.Page("from_url.py", title="von URL", icon=":material/web:")
from_file = st.Page("from_file.py", title="von Datei", icon=":material/folder_open:")

pg = st.navigation({"Glossar erstellen": [from_text, from_url, from_file]})
st.set_page_config(
    page_title="GlossarisiererZH",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)
pg.run()

USER_WARNING = """
⚠️ :red[**Achtung: Nutze die App nur für öffentliche, nicht sensible Daten, da diese auf externen Rechnern von Drittanbietern verarbeitet werden**] (OpenRouter, ausgewählte Modellanbieter, Jina AI usw.).<br><sub>Diese App liefert lediglich einen Entwurf. Überprüfe das Ergebnis immer und passe es an, wenn nötig. Aktuelle App-Version ist v0.2.0. Die letzte Aktualisierung war am 23.12.2025.
""".strip()

with st.sidebar:
    st.caption(USER_WARNING, unsafe_allow_html=True)
