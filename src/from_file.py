import streamlit as st

from ui_glossary import render_glossary_workflow, set_current_source
from settings import SettingsError
from utils_glossary import get_application_runtime, get_ui_settings

ui = get_ui_settings()

st.markdown(ui.text("app_heading"))
st.markdown(ui.text("app_description"))

uploaded_file = st.file_uploader(
    ui.text("file_input_label"),
    type=["txt"],
    help=ui.text("file_input_help"),
)
if st.button(ui.text("file_process_button"), key="from_file_process"):
    if uploaded_file is None:
        st.error(ui.text("file_missing"))
    else:
        try:
            settings, _ = get_application_runtime()
            if uploaded_file.size > settings.limits.max_upload_bytes:
                raise ValueError(
                    ui.text(
                        "file_too_large", max_bytes=settings.limits.max_upload_bytes
                    )
                )
            content = uploaded_file.getvalue().decode("utf-8")
        except UnicodeDecodeError:
            st.error(ui.text("file_invalid_encoding"))
        except SettingsError:
            st.error(ui.text("configuration_error"))
        except ValueError as error:
            st.error(str(error))
        else:
            set_current_source("from_file", content, uploaded_file.name)

render_glossary_workflow("from_file")
