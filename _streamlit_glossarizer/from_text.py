import streamlit as st

from ui_glossary import render_glossary_workflow, set_current_source


st.markdown("### 🤓 GlossarisiererZH")
st.markdown("""
Diese App findet schwer verständliche Begriffe in Texten und erstellt Erklärungen in Leichter Sprache für Glossareinträge.
""")

text_input = st.text_area(
    "Text zur Analyse eingeben", height=300, key="from_text_input"
)
if st.button("Schritt 1: Begriffe erkennen", key="from_text_process") and text_input:
    set_current_source("from_text", text_input, "Glossar")

render_glossary_workflow("from_text")
