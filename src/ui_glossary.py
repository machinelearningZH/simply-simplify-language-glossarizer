import streamlit as st

from utils_glossary import (
    InputLimitError,
    ProviderCallError,
    build_glossary_dataframe,
    clear_derived_session_state,
    create_explanations,
    extract_terms_from_text,
    get_ui_settings,
    make_export_data,
    reset_all_session_states,
    safe_filename_stem,
    zurich_timestamp,
)


def set_current_source(prefix: str, text: str, filename_stem: str) -> None:
    """Store a new source and invalidate every result derived from the old one."""
    clear_derived_session_state(prefix)
    st.session_state[f"{prefix}_current_text"] = text
    st.session_state[f"{prefix}_filename_stem"] = safe_filename_stem(
        filename_stem, get_ui_settings().text("default_filename")
    )


def render_glossary_workflow(prefix: str) -> None:
    """Render the shared extraction, editing, generation, and export workflow."""
    text_key = f"{prefix}_current_text"
    terms_key = f"{prefix}_extracted_terms"
    explanations_key = f"{prefix}_explanations"
    context_key = f"{prefix}_explanations_with_context"
    ui = get_ui_settings()
    if text_key not in st.session_state:
        return

    if terms_key not in st.session_state:
        try:
            with st.spinner(ui.text("extracting_spinner")):
                terms = extract_terms_from_text(st.session_state[text_key])
        except (InputLimitError, ProviderCallError) as error:
            st.error(str(error))
            return
        if not terms or terms == ["Keine Begriffe gefunden"]:
            st.error(ui.text("no_terms_found"))
            return
        st.session_state[terms_key] = terms
        st.success(ui.text("terms_found", count=len(terms)))
        st.rerun()

    st.success(ui.text("terms_found", count=len(st.session_state[terms_key])))
    st.subheader(ui.text("edit_terms_heading"))
    terms_text = st.text_area(
        ui.text("edit_terms_label"),
        value="\n".join(st.session_state[terms_key]),
        height=200,
        key=f"{prefix}_terms_editor",
    )
    st.session_state[terms_key] = [
        term.strip() for term in terms_text.splitlines() if term.strip()
    ]

    if st.button(
        ui.text("generate_button"),
        key=f"{prefix}_generate_explanations",
        disabled=not st.session_state[terms_key],
    ):
        try:
            with st.spinner(ui.text("generating_spinner")):
                explanations, contextual = create_explanations(
                    st.session_state[terms_key], st.session_state[text_key]
                )
        except (InputLimitError, ProviderCallError) as error:
            st.error(str(error))
        else:
            st.session_state[explanations_key] = explanations
            st.session_state[context_key] = contextual
            st.success(ui.text("generated_success"))
            st.rerun()

    if explanations_key not in st.session_state:
        return

    st.success(ui.text("generated_success"))
    st.subheader(ui.text("results_heading"))
    frame = build_glossary_dataframe(
        st.session_state[explanations_key], st.session_state.get(context_key)
    )
    st.dataframe(frame)

    excel_data, csv_data = make_export_data(frame)
    timestamp = zurich_timestamp()
    stem = st.session_state.get(f"{prefix}_filename_stem", ui.text("default_filename"))
    filename = f"{stem}_{timestamp}"
    excel_column, csv_column, _ = st.columns([1, 1, 2])
    with excel_column:
        st.download_button(
            label=ui.text("excel_download"),
            data=excel_data,
            file_name=f"{filename}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with csv_column:
        st.download_button(
            label=ui.text("csv_download"),
            data=csv_data,
            file_name=f"{filename}.csv",
            mime="text/csv",
        )

    if st.button(
        ui.text("reset_button"), type="primary", on_click=reset_all_session_states
    ):
        st.rerun()
