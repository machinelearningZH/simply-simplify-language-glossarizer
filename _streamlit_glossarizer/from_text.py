import streamlit as st
import pandas as pd
import datetime
import io

from utils_glossary import (
    extract_terms_from_text,
    create_explanations,
    clean_text,
    reset_all_session_states,
)


st.markdown("### 🤓 GlossarisiererZH")
st.markdown("""
Diese App findet schwer verständliche Begriffe in Texten und erstellt Erklärungen in Leichter Sprache für Glossareinträge.
""")

if "text_input" not in st.session_state:
    st.session_state.text_input = ""
text_input = st.text_area("Text zur Analyse eingeben", height=300, key="text_input")
process_text_button = st.button("Schritt 1: Begriffe erkennen", key="process_text")

if process_text_button and text_input:
    st.session_state.from_text_current_text = text_input


# If we have text to process
if "from_text_current_text" in st.session_state:
    # Step 1: Extract terms
    if "from_text_extracted_terms" not in st.session_state:
        st.session_state.from_text_extracted_terms = extract_terms_from_text(
            st.session_state.from_text_current_text
        )
        if (
            st.session_state.from_text_extracted_terms
            and st.session_state.from_text_extracted_terms
            != ["Keine Begriffe gefunden"]
        ):
            st.success(
                f"{len(st.session_state.from_text_extracted_terms)} Begriffe gefunden."
            )
            st.rerun()
        else:
            st.error("Keine Begriffe gefunden.")
    else:
        st.success(
            f"{len(st.session_state.from_text_extracted_terms)} Begriffe gefunden."
        )

        # Allow editing the terms
        st.subheader("Begriffe bearbeiten")
        terms_text = st.text_area(
            "Begriffe bearbeiten, hinzufügen oder entfernen (ein Begriff pro Zeile)",
            value="\n".join(st.session_state.from_text_extracted_terms),
            height=200,
            key="terms_editor",
        )
        st.session_state.from_text_extracted_terms = [
            term.strip() for term in terms_text.split("\n") if term.strip()
        ]

        # Step 2: Generate explanations
        generate_button = st.button(
            "Schritt 2: Erklärungen generieren", key="generate_explanations"
        )
        if generate_button:
            with st.spinner("Erklärungen werden generiert..."):
                explanations, explanations_with_context = create_explanations(
                    st.session_state.from_text_extracted_terms,
                    st.session_state.from_text_current_text,
                )

                if explanations:
                    st.session_state.from_text_explanations = explanations
                    st.session_state.from_text_explanations_with_context = (
                        explanations_with_context
                    )
                    st.success("Erklärungen wurden generiert.")
                    st.rerun()
                else:
                    st.error("Erklärungen konnten nicht generiert werden.")

        # Show results only if they exist
        if "from_text_explanations" in st.session_state:
            st.success("Erklärungen wurden generiert!")
            st.subheader("Ergebnisse")

            explanations_parsed = [
                (elem.begriff, elem.erklaerung.text)
                for elem in st.session_state.from_text_explanations.begriffe
            ]
            df = pd.DataFrame(
                explanations_parsed, columns=["Begriff", "Erklärung ohne Kontext"]
            )

            if st.session_state.from_text_explanations_with_context:
                explanations_with_context_parsed = [
                    (elem.begriff, elem.erklaerung.text)
                    for elem in st.session_state.from_text_explanations_with_context.begriffe
                ]
                df_context = pd.DataFrame(
                    explanations_with_context_parsed,
                    columns=["Begriff", "Erklärung mit Kontext"],
                )
                df = pd.merge(df, df_context, on="Begriff", how="outer")

            # Clean text and sort
            try:
                for col in df.columns:
                    if col != "Begriff":
                        df[col] = df[col].apply(clean_text)
                df.sort_values(by="Begriff", inplace=True)
                df.reset_index(drop=True, inplace=True)
            except Exception as e:
                st.error(f"Fehler beim Verarbeiten der Daten: {e}. Bitte versuche es erneut.")
                st.stop()

            # Display results
            st.dataframe(df)

            # Download buttons
            col1, col2, _ = st.columns([1, 1, 2])

            # Generate timestamp
            now = datetime.datetime.now()
            zurich_timezone = datetime.timezone(
                datetime.timedelta(hours=1), name="Europe/Zurich"
            )
            timestamp = now.replace(tzinfo=zurich_timezone).strftime("%Y%m%d_%H%M")

            with col1:
                excel_filename = f"Glossar_{timestamp}.xlsx"
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
                    df.to_excel(writer, index=False, sheet_name="Glossar")
                excel_buffer.seek(0)
                st.download_button(
                    label="Excel herunterladen",
                    data=excel_buffer,
                    file_name=excel_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

            with col2:
                csv_filename = f"Glossar_{timestamp}.csv"
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False)
                st.download_button(
                    label="CSV herunterladen",
                    data=csv_buffer.getvalue().encode("utf-8"),
                    file_name=csv_filename,
                    mime="text/csv",
                )

            # Reset button
            if st.button(
                "Neu starten", type="primary", on_click=reset_all_session_states
            ):
                st.rerun()
