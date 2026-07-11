import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from urllib.parse import urlparse

import yaml
from dotenv import dotenv_values

MODULE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = MODULE_DIR / "config.yaml"
ENV_PATH = MODULE_DIR / ".env"


class SettingsError(ValueError):
    """Report invalid or missing application configuration."""


@dataclass(frozen=True)
class OpenRouterSettings:
    api_key: str = field(repr=False)
    base_url: str
    model: str
    max_output_tokens: int
    timeout_seconds: float
    max_retries: int


@dataclass(frozen=True)
class ReaderSettings:
    base_url: str
    timeout_seconds: float
    max_response_bytes: int


@dataclass(frozen=True)
class InputLimits:
    max_input_chars: int
    max_upload_bytes: int
    max_terms: int
    max_term_chars: int


@dataclass(frozen=True)
class ApplicationSettings:
    openrouter: OpenRouterSettings
    reader: ReaderSettings
    limits: InputLimits


def _require_field(config: Mapping[str, object], name: str) -> object:
    try:
        return config[name]
    except KeyError as error:
        raise SettingsError(f"Missing setting: {name}") from error


def _validate_https_url(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise SettingsError(f"{name} must be an HTTPS URL")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SettingsError(f"{name} must be an HTTPS URL")
    return value


def _validate_model(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SettingsError("model must be a non-empty string")
    return value


def _validate_positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SettingsError(f"{name} must be a positive integer")
    return value


def _validate_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SettingsError("timeout_seconds must be a positive number")
    result = float(value)
    if not isfinite(result) or result <= 0:
        raise SettingsError("timeout_seconds must be a positive number")
    return result


def _validate_max_retries(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SettingsError("max_retries must be a non-negative integer")
    return value


def load_application_settings(
    config_path: Path = CONFIG_PATH,
    env_path: Path = ENV_PATH,
) -> ApplicationSettings:
    """Load and validate application settings without exposing credentials."""
    try:
        config_text = config_path.read_text(encoding="utf-8")
        raw_config = yaml.safe_load(config_text)
        if not isinstance(raw_config, Mapping):
            raise SettingsError("Configuration must be a mapping")
        openrouter = raw_config["openrouter"]
        if not isinstance(openrouter, Mapping):
            raise SettingsError("openrouter must be a mapping")
        reader = raw_config["reader"]
        if not isinstance(reader, Mapping):
            raise SettingsError("reader must be a mapping")
        limits = raw_config["limits"]
        if not isinstance(limits, Mapping):
            raise SettingsError("limits must be a mapping")

        env_values = dotenv_values(env_path)
        api_key = os.getenv("OPENROUTER_API_KEY") or env_values.get(
            "OPENROUTER_API_KEY"
        )
        if not api_key:
            raise SettingsError("OPENROUTER_API_KEY is missing")

        return ApplicationSettings(
            openrouter=OpenRouterSettings(
                api_key=api_key,
                base_url=_validate_https_url(
                    _require_field(openrouter, "base_url"), "base_url"
                ),
                model=_validate_model(_require_field(openrouter, "model")),
                max_output_tokens=_validate_positive_integer(
                    _require_field(openrouter, "max_output_tokens"),
                    "max_output_tokens",
                ),
                timeout_seconds=_validate_timeout(
                    _require_field(openrouter, "timeout_seconds")
                ),
                max_retries=_validate_max_retries(
                    _require_field(openrouter, "max_retries")
                ),
            ),
            reader=ReaderSettings(
                base_url=_validate_https_url(
                    _require_field(reader, "base_url"), "reader.base_url"
                ),
                timeout_seconds=_validate_timeout(
                    _require_field(reader, "timeout_seconds")
                ),
                max_response_bytes=_validate_positive_integer(
                    _require_field(reader, "max_response_bytes"),
                    "max_response_bytes",
                ),
            ),
            limits=InputLimits(
                max_input_chars=_validate_positive_integer(
                    _require_field(limits, "max_input_chars"), "max_input_chars"
                ),
                max_upload_bytes=_validate_positive_integer(
                    _require_field(limits, "max_upload_bytes"), "max_upload_bytes"
                ),
                max_terms=_validate_positive_integer(
                    _require_field(limits, "max_terms"), "max_terms"
                ),
                max_term_chars=_validate_positive_integer(
                    _require_field(limits, "max_term_chars"), "max_term_chars"
                ),
            ),
        )
    except SettingsError:
        raise
    except OSError as error:
        raise SettingsError(f"Unable to read configuration: {config_path}") from error
    except yaml.YAMLError as error:
        raise SettingsError(f"Invalid YAML configuration: {config_path}") from error
    except KeyError as error:
        raise SettingsError(f"Missing configuration field: {error.args[0]}") from error
    except (TypeError, ValueError) as error:
        raise SettingsError(f"Invalid application configuration: {error}") from error


def load_openrouter_settings(
    config_path: Path = CONFIG_PATH,
    env_path: Path = ENV_PATH,
) -> OpenRouterSettings:
    """Load only the OpenRouter section for callers that need provider settings."""
    return load_application_settings(config_path, env_path).openrouter
