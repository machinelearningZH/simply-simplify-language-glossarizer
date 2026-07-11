import ui_glossary
import utils_glossary


def test_set_current_source_invalidates_old_results(monkeypatch):
    state = {
        "from_text_current_text": "old text",
        "from_text_extracted_terms": ["old term"],
        "from_text_explanations": object(),
        "from_text_explanations_with_context": object(),
        "from_text_terms_editor": "old term",
    }
    monkeypatch.setattr(ui_glossary.st, "session_state", state)
    monkeypatch.setattr(utils_glossary.st, "session_state", state)

    ui_glossary.set_current_source("from_text", "new text", "new source.txt")

    assert state == {
        "from_text_current_text": "new text",
        "from_text_filename_stem": "new_source",
    }
