from urllib.parse import urlparse

import streamlit as st

from ui_glossary import render_glossary_workflow, set_current_source
from settings import SettingsError
from utils_glossary import ReaderError, convert_url_to_markdown, get_application_runtime


st.markdown("### 🤓 GlossarisiererZH")
st.markdown("""
Diese App findet schwer verständliche Begriffe in Texten und erstellt Erklärungen in Leichter Sprache für Glossareinträge.
""")

url_input = st.text_input("URL eingeben", placeholder="https://zh.ch")
if st.button("Schritt 1: URL verarbeiten", key="from_url_process") and url_input:
    try:
        settings, _ = get_application_runtime()
        with st.spinner("Text von Webseite lesen..."):
            markdown_content = convert_url_to_markdown(url_input, settings.reader)
    except ReaderError as error:
        st.error(str(error))
    except SettingsError:
        st.error("Die Anwendung ist nicht korrekt konfiguriert.")
    else:
        path = urlparse(url_input).path.rstrip("/")
        filename_stem = path.rsplit("/", maxsplit=1)[-1] or "glossar"
        set_current_source("from_url", markdown_content, filename_stem)

render_glossary_workflow("from_url")
