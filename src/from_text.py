import streamlit as st

from ui_glossary import render_glossary_workflow, set_current_source
from utils_glossary import get_ui_settings

ui = get_ui_settings()

st.markdown(ui.text("app_heading"))
st.markdown(ui.text("app_description"))

text_input = st.text_area(
    ui.text("text_input_label"), height=300, key="from_text_input"
)
if st.button(ui.text("text_process_button"), key="from_text_process") and text_input:
    set_current_source("from_text", text_input, ui.text("text_filename"))

render_glossary_workflow("from_text")
