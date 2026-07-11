import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import openai
import pandas as pd
import pytest
import utils_glossary
from settings import InputLimits, OpenRouterSettings, ReaderSettings, SettingsError


def make_settings() -> OpenRouterSettings:
    return OpenRouterSettings(
        api_key="secret-key",
        base_url="https://openrouter.ai/api/v1",
        model="google/gemini-3-flash-preview",
        max_output_tokens=8192,
        timeout_seconds=60.0,
        max_retries=2,
    )


def test_create_openrouter_client_uses_explicit_provider_settings(monkeypatch):
    constructor = Mock(return_value=object())
    monkeypatch.setattr(utils_glossary, "OpenAI", constructor)

    client = utils_glossary.create_openrouter_client(make_settings())

    assert client is constructor.return_value
    constructor.assert_called_once_with(
        api_key="secret-key",
        base_url="https://openrouter.ai/api/v1",
        timeout=60.0,
        max_retries=2,
    )


def test_call_openrouter_requests_and_validates_structured_output(monkeypatch):
    settings = make_settings()
    client = Mock()
    content = json.dumps({"terms": [{"term": "Fachbegriff"}]})
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    monkeypatch.setattr(
        utils_glossary, "get_openrouter_runtime", lambda: (settings, client)
    )

    result = utils_glossary.call_openrouter("prompt", utils_glossary.TermList)

    assert result.terms[0].term == "Fachbegriff"
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == settings.model
    assert kwargs["messages"] == [{"role": "user", "content": "prompt"}]
    assert kwargs["max_tokens"] == settings.max_output_tokens
    assert "temperature" not in kwargs
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["strict"] is True


def test_call_openrouter_returns_plain_text(monkeypatch):
    settings = make_settings()
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Antwort"))]
    )
    monkeypatch.setattr(
        utils_glossary, "get_openrouter_runtime", lambda: (settings, client)
    )

    assert utils_glossary.call_openrouter("prompt") == "Antwort"


def test_call_openrouter_reports_configuration_error_without_secret(monkeypatch):
    error = SettingsError("OPENROUTER_API_KEY fehlt: secret-key")
    monkeypatch.setattr(
        utils_glossary, "get_openrouter_runtime", Mock(side_effect=error)
    )
    with pytest.raises(utils_glossary.ProviderCallError) as caught:
        utils_glossary.call_openrouter("prompt")

    assert "secret-key" not in str(caught.value)


def test_call_openrouter_reports_provider_error(monkeypatch):
    settings = make_settings()
    client = Mock()
    client.chat.completions.create.side_effect = openai.OpenAIError(
        "Authorization: Bearer secret-key; provider body: private prompt"
    )
    monkeypatch.setattr(
        utils_glossary, "get_openrouter_runtime", lambda: (settings, client)
    )
    with pytest.raises(utils_glossary.ProviderCallError) as caught:
        utils_glossary.call_openrouter("prompt")

    message = str(caught.value)
    assert "secret-key" not in message
    assert "private prompt" not in message


def test_clear_derived_session_state_preserves_current_source(monkeypatch):
    state = {
        "from_text_current_text": "new",
        "from_text_extracted_terms": ["old"],
        "from_text_explanations": object(),
        "from_url_extracted_terms": ["other page"],
    }
    monkeypatch.setattr(utils_glossary.st, "session_state", state)

    utils_glossary.clear_derived_session_state("from_text")

    assert state == {
        "from_text_current_text": "new",
        "from_url_extracted_terms": ["other page"],
    }


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
def test_spreadsheet_values_are_neutralized(prefix):
    assert utils_glossary.sanitize_spreadsheet_value(f"{prefix}cmd") == f"'{prefix}cmd"


def test_export_data_sanitizes_csv_and_creates_excel():
    frame = pd.DataFrame([{"Begriff": "=1+1", "Erklärung": "ordinary"}])

    excel_data, csv_data = utils_glossary.make_export_data(frame)

    assert excel_data.startswith(b"PK")
    assert b"'=1+1" in csv_data


def test_build_glossary_dataframe_collapses_duplicate_provider_terms():
    explanations = utils_glossary.ExplanationList.model_validate(
        {
            "begriffe": [
                {"begriff": "Bund", "erklaerung": {"text": "alt"}},
                {"begriff": "Bund", "erklaerung": {"text": "neu"}},
            ]
        }
    )

    frame = utils_glossary.build_glossary_dataframe(explanations, None)

    assert frame.to_dict("records") == [
        {"Begriff": "Bund", "Erklärung ohne Kontext": "neu"}
    ]


def test_validate_terms_rejects_empty_list():
    limits = InputLimits(
        max_input_chars=100,
        max_upload_bytes=200,
        max_terms=2,
        max_term_chars=10,
    )

    with pytest.raises(utils_glossary.InputLimitError, match="mindestens"):
        utils_glossary.validate_terms([], limits)


def test_zurich_timestamp_converts_summer_time():
    utc_now = datetime(2026, 7, 11, 12, 30, tzinfo=timezone.utc)

    assert utils_glossary.zurich_timestamp(utc_now) == "20260711_1430"


class FakeResponse:
    encoding = "utf-8"

    def __init__(self, chunks, *, error=None):
        self.chunks = chunks
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def raise_for_status(self):
        if self.error:
            raise self.error

    def iter_content(self, chunk_size):
        return iter(self.chunks)


def reader_settings(max_response_bytes=100):
    return ReaderSettings(
        base_url="https://r.jina.ai/",
        timeout_seconds=5.0,
        max_response_bytes=max_response_bytes,
    )


def test_convert_url_to_markdown_uses_timeout_and_streaming(monkeypatch):
    get = Mock(return_value=FakeResponse(["Grüezi".encode()]))
    monkeypatch.setattr(utils_glossary.requests, "get", get)

    result = utils_glossary.convert_url_to_markdown(
        "https://example.com/page", reader_settings()
    )

    assert result == "Grüezi"
    get.assert_called_once_with(
        "https://r.jina.ai/https://example.com/page", timeout=5.0, stream=True
    )


def test_convert_url_to_markdown_rejects_oversized_response(monkeypatch):
    monkeypatch.setattr(
        utils_glossary.requests,
        "get",
        Mock(return_value=FakeResponse([b"too large"])),
    )

    with pytest.raises(utils_glossary.ReaderError, match="zu gross"):
        utils_glossary.convert_url_to_markdown(
            "https://example.com", reader_settings(max_response_bytes=3)
        )


def test_convert_url_to_markdown_redacts_network_failure(monkeypatch):
    monkeypatch.setattr(
        utils_glossary.requests,
        "get",
        Mock(side_effect=utils_glossary.requests.Timeout("private URL details")),
    )

    with pytest.raises(utils_glossary.ReaderError) as caught:
        utils_glossary.convert_url_to_markdown("https://example.com", reader_settings())

    assert "private URL details" not in str(caught.value)
