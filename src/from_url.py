from urllib.parse import urlparse

import streamlit as st

from ui_glossary import render_glossary_workflow, set_current_source
from settings import SettingsError
from utils_glossary import (
    ReaderError,
    convert_url_to_markdown,
    get_application_runtime,
    get_ui_settings,
)

ui = get_ui_settings()

st.markdown(ui.text("app_heading"))
st.markdown(ui.text("app_description"))

url_input = st.text_input(
    ui.text("url_input_label"), placeholder=ui.text("url_input_placeholder")
)
if st.button(ui.text("url_process_button"), key="from_url_process") and url_input:
    try:
        settings, _ = get_application_runtime()
        with st.spinner(ui.text("url_reading_spinner")):
            markdown_content = convert_url_to_markdown(url_input, settings.reader)
    except ReaderError as error:
        st.error(str(error))
    except SettingsError:
        st.error(ui.text("configuration_error"))
    else:
        path = urlparse(url_input).path.rstrip("/")
        filename_stem = path.rsplit("/", maxsplit=1)[-1] or ui.text("default_filename")
        set_current_source("from_url", markdown_content, filename_stem)

render_glossary_workflow("from_url")
