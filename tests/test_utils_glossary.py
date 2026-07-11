import json
from types import SimpleNamespace
from unittest.mock import Mock

import openai
import utils_glossary
from settings import OpenRouterSettings, SettingsError


def make_settings() -> OpenRouterSettings:
    return OpenRouterSettings(
        api_key="secret-key",
        base_url="https://openrouter.ai/api/v1",
        model="google/gemini-3-flash-preview",
        temperature=0.0,
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
    assert kwargs["temperature"] == settings.temperature
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
    streamlit_error = Mock()
    monkeypatch.setattr(utils_glossary.st, "error", streamlit_error)

    assert utils_glossary.call_openrouter("prompt") is None
    message = streamlit_error.call_args.args[0]
    assert message == (
        "OpenRouter ist nicht korrekt konfiguriert. "
        "Bitte prüfe die Anwendungseinstellungen."
    )
    assert "secret-key" not in message


def test_call_openrouter_reports_provider_error(monkeypatch):
    settings = make_settings()
    client = Mock()
    client.chat.completions.create.side_effect = openai.OpenAIError(
        "Authorization: Bearer secret-key; provider body: private prompt"
    )
    monkeypatch.setattr(
        utils_glossary, "get_openrouter_runtime", lambda: (settings, client)
    )
    streamlit_error = Mock()
    monkeypatch.setattr(utils_glossary.st, "error", streamlit_error)

    assert utils_glossary.call_openrouter("prompt") is None
    message = streamlit_error.call_args.args[0]
    assert message == (
        "OpenRouter konnte die Anfrage nicht verarbeiten. "
        "Bitte versuche es später erneut."
    )
    assert "secret-key" not in message
    assert "private prompt" not in message
