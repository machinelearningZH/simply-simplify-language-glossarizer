from pathlib import Path

import pytest

from _streamlit_glossarizer.settings import (
    SettingsError,
    load_application_settings,
    load_openrouter_settings,
)


def write_config(path: Path, *, model: str = "provider/model") -> None:
    path.write_text(
        f"""openrouter:
  base_url: https://openrouter.ai/api/v1
  model: {model}
  max_output_tokens: 2048
  timeout_seconds: 30.0
  max_retries: 3
reader:
  base_url: https://r.jina.ai/
  timeout_seconds: 15.0
  max_response_bytes: 1000000
limits:
  max_input_chars: 50000
  max_upload_bytes: 200000
  max_terms: 100
  max_term_chars: 150
""",
        encoding="utf-8",
    )


def test_load_openrouter_settings_reads_yaml_and_environment(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-key")

    settings = load_openrouter_settings(config_path, tmp_path / ".env")

    assert settings.api_key == "secret-key"
    assert settings.base_url == "https://openrouter.ai/api/v1"
    assert settings.model == "provider/model"
    assert settings.max_output_tokens == 2048
    assert settings.timeout_seconds == 30.0
    assert settings.max_retries == 3
    assert "secret-key" not in repr(settings)


def test_load_application_settings_reads_reader_and_input_limits(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-key")

    settings = load_application_settings(config_path, tmp_path / ".env")

    assert settings.reader.base_url == "https://r.jina.ai/"
    assert settings.reader.timeout_seconds == 15.0
    assert settings.reader.max_response_bytes == 1_000_000
    assert settings.limits.max_input_chars == 50_000
    assert settings.limits.max_upload_bytes == 200_000
    assert settings.limits.max_terms == 100
    assert settings.limits.max_term_chars == 150


def test_load_openrouter_settings_uses_module_relative_env_file(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"
    write_config(config_path)
    env_path.write_text("OPENROUTER_API_KEY=env-file-key\n", encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    settings = load_openrouter_settings(config_path, env_path)

    assert settings.api_key == "env-file-key"


def test_load_openrouter_settings_rejects_missing_key(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(SettingsError, match="OPENROUTER_API_KEY"):
        load_openrouter_settings(config_path, tmp_path / "missing.env")


def test_load_openrouter_settings_reports_invalid_yaml_concisely(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("openrouter: [\n", encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-key")

    with pytest.raises(SettingsError, match="Invalid YAML configuration"):
        load_openrouter_settings(config_path, tmp_path / ".env")


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ("max_output_tokens: 0", "max_output_tokens"),
        ("max_output_tokens: 1.5", "max_output_tokens"),
        ("max_output_tokens: true", "max_output_tokens"),
        ("timeout_seconds: 0", "timeout_seconds"),
        ("timeout_seconds: true", "timeout_seconds"),
        ("timeout_seconds: .nan", "timeout_seconds"),
        ("timeout_seconds: .inf", "timeout_seconds"),
        ("max_retries: -1", "max_retries"),
        ("max_retries: 1.5", "max_retries"),
        ("max_retries: true", "max_retries"),
        ("base_url: http://openrouter.ai/api/v1", "base_url"),
        ("base_url: 42", "base_url"),
        ("model: '   '", "model"),
        ("model: 42", "model"),
    ],
)
def test_load_openrouter_settings_rejects_invalid_values(
    tmp_path, monkeypatch, replacement, message
):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    text = config_path.read_text(encoding="utf-8")
    key = replacement.split(":", maxsplit=1)[0]
    text = "\n".join(
        f"{line[: len(line) - len(line.lstrip())]}{replacement}"
        if line.strip().startswith(f"{key}:")
        else line
        for line in text.splitlines()
    )
    config_path.write_text(text, encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-key")

    with pytest.raises(SettingsError, match=message):
        load_openrouter_settings(config_path, tmp_path / ".env")
