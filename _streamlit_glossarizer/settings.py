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
    temperature: float
    max_output_tokens: int
    timeout_seconds: float
    max_retries: int


def _require_field(config: Mapping[str, object], name: str) -> object:
    try:
        return config[name]
    except KeyError as error:
        raise SettingsError(f"Missing OpenRouter setting: {name}") from error


def _validate_base_url(value: object) -> str:
    if not isinstance(value, str):
        raise SettingsError("base_url must be an HTTPS URL")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SettingsError("base_url must be an HTTPS URL")
    return value


def _validate_model(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SettingsError("model must be a non-empty string")
    return value


def _validate_temperature(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SettingsError("temperature must be a number from 0 to 2")
    result = float(value)
    if not isfinite(result) or not 0 <= result <= 2:
        raise SettingsError("temperature must be a number from 0 to 2")
    return result


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


def load_openrouter_settings(
    config_path: Path = CONFIG_PATH,
    env_path: Path = ENV_PATH,
) -> OpenRouterSettings:
    """Load and validate OpenRouter settings without exposing credentials."""
    try:
        config_text = config_path.read_text(encoding="utf-8")
        raw_config = yaml.safe_load(config_text)
        if not isinstance(raw_config, Mapping):
            raise SettingsError("Configuration must be a mapping")
        openrouter = raw_config["openrouter"]
        if not isinstance(openrouter, Mapping):
            raise SettingsError("openrouter must be a mapping")

        env_values = dotenv_values(env_path)
        api_key = os.getenv("OPENROUTER_API_KEY") or env_values.get(
            "OPENROUTER_API_KEY"
        )
        if not api_key:
            raise SettingsError("OPENROUTER_API_KEY is missing")

        return OpenRouterSettings(
            api_key=api_key,
            base_url=_validate_base_url(_require_field(openrouter, "base_url")),
            model=_validate_model(_require_field(openrouter, "model")),
            temperature=_validate_temperature(
                _require_field(openrouter, "temperature")
            ),
            max_output_tokens=_validate_positive_integer(
                _require_field(openrouter, "max_output_tokens"), "max_output_tokens"
            ),
            timeout_seconds=_validate_timeout(
                _require_field(openrouter, "timeout_seconds")
            ),
            max_retries=_validate_max_retries(
                _require_field(openrouter, "max_retries")
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
        raise SettingsError(f"Invalid OpenRouter configuration: {error}") from error
