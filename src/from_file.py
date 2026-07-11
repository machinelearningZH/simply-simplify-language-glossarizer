import streamlit as st

from ui_glossary import render_glossary_workflow, set_current_source
from settings import SettingsError
from utils_glossary import get_application_runtime


st.markdown("### 🤓 GlossarisiererZH")
st.markdown("""
Diese App findet schwer verständliche Begriffe in Texten und erstellt Erklärungen in Leichter Sprache für Glossareinträge.
""")

uploaded_file = st.file_uploader(
    "Datei auswählen",
    type=["txt"],
    help="Lade eine UTF-8-kodierte .txt-Datei mit dem zu verarbeitenden Text hoch.",
)
if st.button("Schritt 1: .txt-Datei verarbeiten", key="from_file_process"):
    if uploaded_file is None:
        st.error("Bitte wähle zuerst eine Datei aus.")
    else:
        try:
            settings, _ = get_application_runtime()
            if uploaded_file.size > settings.limits.max_upload_bytes:
                raise ValueError(
                    "Die Datei ist zu gross. "
                    f"Maximal {settings.limits.max_upload_bytes} Bytes sind erlaubt."
                )
            content = uploaded_file.getvalue().decode("utf-8")
        except UnicodeDecodeError:
            st.error("Die Datei muss UTF-8-kodiert sein.")
        except SettingsError:
            st.error("Die Anwendung ist nicht korrekt konfiguriert.")
        except ValueError as error:
            st.error(str(error))
        else:
            set_current_source("from_file", content, uploaded_file.name)

render_glossary_workflow("from_file")
