import streamlit as st

from utils_glossary import (
    InputLimitError,
    ProviderCallError,
    build_glossary_dataframe,
    clear_derived_session_state,
    create_explanations,
    extract_terms_from_text,
    make_export_data,
    reset_all_session_states,
    safe_filename_stem,
    zurich_timestamp,
)


def set_current_source(prefix: str, text: str, filename_stem: str) -> None:
    """Store a new source and invalidate every result derived from the old one."""
    clear_derived_session_state(prefix)
    st.session_state[f"{prefix}_current_text"] = text
    st.session_state[f"{prefix}_filename_stem"] = safe_filename_stem(filename_stem)


def render_glossary_workflow(prefix: str) -> None:
    """Render the shared extraction, editing, generation, and export workflow."""
    text_key = f"{prefix}_current_text"
    terms_key = f"{prefix}_extracted_terms"
    explanations_key = f"{prefix}_explanations"
    context_key = f"{prefix}_explanations_with_context"
    if text_key not in st.session_state:
        return

    if terms_key not in st.session_state:
        try:
            with st.spinner("Begriffe aus dem Text extrahieren..."):
                terms = extract_terms_from_text(st.session_state[text_key])
        except (InputLimitError, ProviderCallError) as error:
            st.error(str(error))
            return
        if not terms or terms == ["Keine Begriffe gefunden"]:
            st.error("Keine Begriffe gefunden.")
            return
        st.session_state[terms_key] = terms
        st.success(f"{len(terms)} Begriffe gefunden.")
        st.rerun()

    st.success(f"{len(st.session_state[terms_key])} Begriffe gefunden.")
    st.subheader("Begriffe bearbeiten")
    terms_text = st.text_area(
        "Begriffe bearbeiten, hinzufügen oder entfernen (ein Begriff pro Zeile)",
        value="\n".join(st.session_state[terms_key]),
        height=200,
        key=f"{prefix}_terms_editor",
    )
    st.session_state[terms_key] = [
        term.strip() for term in terms_text.splitlines() if term.strip()
    ]

    if st.button(
        "Schritt 2: Erklärungen generieren",
        key=f"{prefix}_generate_explanations",
        disabled=not st.session_state[terms_key],
    ):
        try:
            with st.spinner("Erklärungen werden generiert..."):
                explanations, contextual = create_explanations(
                    st.session_state[terms_key], st.session_state[text_key]
                )
        except (InputLimitError, ProviderCallError) as error:
            st.error(str(error))
        else:
            st.session_state[explanations_key] = explanations
            st.session_state[context_key] = contextual
            st.success("Erklärungen wurden generiert.")
            st.rerun()

    if explanations_key not in st.session_state:
        return

    st.success("Erklärungen wurden generiert!")
    st.subheader("Ergebnisse")
    frame = build_glossary_dataframe(
        st.session_state[explanations_key], st.session_state.get(context_key)
    )
    st.dataframe(frame)

    excel_data, csv_data = make_export_data(frame)
    timestamp = zurich_timestamp()
    stem = st.session_state.get(f"{prefix}_filename_stem", "glossar")
    filename = f"{stem}_{timestamp}"
    excel_column, csv_column, _ = st.columns([1, 1, 2])
    with excel_column:
        st.download_button(
            label="Excel herunterladen",
            data=excel_data,
            file_name=f"{filename}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with csv_column:
        st.download_button(
            label="CSV herunterladen",
            data=csv_data,
            file_name=f"{filename}.csv",
            mime="text/csv",
        )

    if st.button("Neu starten", type="primary", on_click=reset_all_session_states):
        st.rerun()
