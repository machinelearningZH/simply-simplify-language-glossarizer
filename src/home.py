import streamlit as st

from settings import load_ui_settings

ui = load_ui_settings()
st.set_page_config(
    page_title=ui.text("page_title"),
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)

from_text = st.Page(
    "from_text.py", title=ui.text("navigation_text"), icon=":material/description:"
)
from_url = st.Page(
    "from_url.py", title=ui.text("navigation_url"), icon=":material/web:"
)
from_file = st.Page(
    "from_file.py", title=ui.text("navigation_file"), icon=":material/folder_open:"
)

pg = st.navigation({ui.text("navigation_section"): [from_text, from_url, from_file]})
pg.run()

with st.sidebar:
    st.caption(ui.text("sidebar_warning"), unsafe_allow_html=True)
