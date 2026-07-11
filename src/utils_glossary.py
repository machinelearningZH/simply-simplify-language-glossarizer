import datetime
import io
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import openai
import pandas as pd
import requests
import streamlit as st
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from settings import (
    ApplicationSettings,
    InputLimits,
    OpenRouterSettings,
    ReaderSettings,
    SettingsError,
    load_application_settings,
)
from utils_prompts_glossary import (
    CREATE_GLOSSARY,
    CREATE_GLOSSARY_FROM_CONTEXT,
    EXTRACT_TERMS,
)


class JSONFormatter(logging.Formatter):
    """Format operational events without including prompts or provider bodies."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "timestamp": self.formatTime(record, self.datefmt),
        }
        if error_type := getattr(record, "error_type", None):
            payload["error_type"] = error_type
        return json.dumps(payload)


logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


class ProviderCallError(RuntimeError):
    """Report a provider failure without carrying sensitive provider content."""


class ReaderError(RuntimeError):
    """Report a safe, user-facing URL reader failure."""


class InputLimitError(ValueError):
    """Report input that exceeds configured application limits."""


class Term(BaseModel):
    term: str


class TermList(BaseModel):
    terms: list[Term]


class Explanation(BaseModel):
    text: str


class ExplanationElement(BaseModel):
    begriff: str
    erklaerung: Explanation


class ExplanationList(BaseModel):
    begriffe: list[ExplanationElement]


def create_openrouter_client(settings: OpenRouterSettings) -> OpenAI:
    """Create an OpenRouter client from validated provider settings."""
    return OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )


@st.cache_resource
def get_application_runtime() -> tuple[ApplicationSettings, OpenAI]:
    """Load settings and construct the shared provider client lazily."""
    settings = load_application_settings()
    return settings, create_openrouter_client(settings.openrouter)


def get_openrouter_runtime() -> tuple[OpenRouterSettings, OpenAI]:
    """Return the provider-specific portion of the application runtime."""
    settings, client = get_application_runtime()
    return settings.openrouter, client


def _call_openrouter(
    prompt: str,
    settings: OpenRouterSettings,
    client: OpenAI,
    response_format: type[BaseModel] | None = None,
) -> BaseModel | str:
    request: dict[str, object] = {
        "model": settings.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": settings.max_output_tokens,
    }
    if response_format is not None:
        request["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": response_format.__name__,
                "strict": True,
                "schema": response_format.model_json_schema(),
            },
        }

    try:
        completion = client.chat.completions.create(**request)
        content = completion.choices[0].message.content
        if not content:
            raise ValueError("empty response")
        return (
            response_format.model_validate_json(content) if response_format else content
        )
    except (
        openai.OpenAIError,
        ValidationError,
        ValueError,
        IndexError,
        AttributeError,
    ) as error:
        logger.error(
            "OpenRouter request failed",
            extra={"error_type": type(error).__name__},
        )
        raise ProviderCallError(
            "OpenRouter konnte die Anfrage nicht verarbeiten. "
            "Bitte versuche es später erneut."
        ) from None


def call_openrouter(
    prompt: str,
    response_format: type[BaseModel] | None = None,
) -> BaseModel | str:
    """Call OpenRouter and raise a sanitized error on failure."""
    try:
        settings, client = get_openrouter_runtime()
    except SettingsError:
        logger.error("OpenRouter configuration is invalid")
        raise ProviderCallError(
            "OpenRouter ist nicht korrekt konfiguriert. "
            "Bitte prüfe die Anwendungseinstellungen."
        ) from None
    return _call_openrouter(prompt, settings, client, response_format)


def validate_text(text: str, limits: InputLimits) -> str:
    """Validate source text before it is included in a provider prompt."""
    if not text.strip():
        raise InputLimitError("Der Text ist leer.")
    if len(text) > limits.max_input_chars:
        raise InputLimitError(
            f"Der Text ist zu lang. Maximal {limits.max_input_chars} Zeichen sind erlaubt."
        )
    return text


def validate_terms(terms: list[str], limits: InputLimits) -> list[str]:
    """Normalize and bound user-editable glossary terms."""
    normalized = list(dict.fromkeys(term.strip() for term in terms if term.strip()))
    if not normalized:
        raise InputLimitError("Bitte gib mindestens einen Begriff ein.")
    if len(normalized) > limits.max_terms:
        raise InputLimitError(f"Es sind maximal {limits.max_terms} Begriffe erlaubt.")
    if any(len(term) > limits.max_term_chars for term in normalized):
        raise InputLimitError(
            f"Ein Begriff darf maximal {limits.max_term_chars} Zeichen lang sein."
        )
    return normalized


def clean_text(text: str) -> str:
    """Remove unwanted Markdown formatting."""
    text = re.sub(r"[*_\#]", "", text)
    return text.replace("ß", "ss").strip()


def reset_all_session_states() -> None:
    """Reset all Streamlit session state."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def clear_derived_session_state(prefix: str) -> None:
    """Remove results that no longer belong to a newly selected source."""
    for suffix in (
        "extracted_terms",
        "explanations",
        "explanations_with_context",
        "terms_editor",
    ):
        st.session_state.pop(f"{prefix}_{suffix}", None)


def extract_terms_from_text(text: str) -> list[str]:
    """Extract difficult terms from bounded source text."""
    try:
        settings, client = get_application_runtime()
    except SettingsError:
        logger.error("Application configuration is invalid")
        raise ProviderCallError(
            "Die Anwendung ist nicht korrekt konfiguriert."
        ) from None
    validate_text(text, settings.limits)
    result = _call_openrouter(
        EXTRACT_TERMS.format(TEXT=text), settings.openrouter, client, TermList
    )
    if not isinstance(result, TermList):
        raise ProviderCallError("OpenRouter hat ein unerwartetes Ergebnis geliefert.")
    return sorted({term.term.strip() for term in result.terms if term.term.strip()})


def create_explanations(
    terms: list[str], text: str | None = None
) -> tuple[ExplanationList, ExplanationList | None]:
    """Create explanations in parallel without calling Streamlit from workers."""
    try:
        application_settings, client = get_application_runtime()
    except SettingsError:
        logger.error("Application configuration is invalid")
        raise ProviderCallError(
            "Die Anwendung ist nicht korrekt konfiguriert."
        ) from None
    normalized_terms = validate_terms(terms, application_settings.limits)
    if text is not None:
        validate_text(text, application_settings.limits)
    terms_str = "\n".join(normalized_terms)
    provider_settings = application_settings.openrouter

    def without_context() -> BaseModel | str:
        return _call_openrouter(
            CREATE_GLOSSARY.format(BEGRIFFE=terms_str),
            provider_settings,
            client,
            ExplanationList,
        )

    def with_context() -> BaseModel | str | None:
        if text is None:
            return None
        return _call_openrouter(
            CREATE_GLOSSARY_FROM_CONTEXT.format(TEXT=text, BEGRIFFE=terms_str),
            provider_settings,
            client,
            ExplanationList,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_without_context = executor.submit(without_context)
        future_with_context = executor.submit(with_context)
        plain_result = future_without_context.result()
        context_result = future_with_context.result()

    if not isinstance(plain_result, ExplanationList) or (
        context_result is not None and not isinstance(context_result, ExplanationList)
    ):
        raise ProviderCallError("OpenRouter hat ein unerwartetes Ergebnis geliefert.")
    return plain_result, context_result


def convert_url_to_markdown(url: str, settings: ReaderSettings) -> str:
    """Convert a public HTTP(S) URL to bounded Markdown through Jina Reader."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ReaderError("Bitte gib eine gültige HTTP- oder HTTPS-URL ein.")

    try:
        with requests.get(
            f"{settings.base_url}{url}",
            timeout=settings.timeout_seconds,
            stream=True,
        ) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                content.extend(chunk)
                if len(content) > settings.max_response_bytes:
                    raise ReaderError("Die gelesene Webseite ist zu gross.")
    except requests.RequestException:
        logger.error("Jina Reader request failed")
        raise ReaderError(
            "Die URL konnte nicht gelesen werden. Bitte versuche es später erneut."
        ) from None

    try:
        return content.decode(response.encoding or "utf-8")
    except UnicodeDecodeError:
        raise ReaderError(
            "Die Webseite verwendet eine nicht unterstützte Kodierung."
        ) from None


def build_glossary_dataframe(
    explanations: ExplanationList,
    explanations_with_context: ExplanationList | None,
) -> pd.DataFrame:
    """Build one row per term and avoid many-to-many merge expansion."""
    plain = {
        item.begriff: clean_text(item.erklaerung.text) for item in explanations.begriffe
    }
    contextual = (
        {
            item.begriff: clean_text(item.erklaerung.text)
            for item in explanations_with_context.begriffe
        }
        if explanations_with_context
        else {}
    )
    terms = sorted(plain.keys() | contextual.keys())
    rows = [
        {
            "Begriff": term,
            "Erklärung ohne Kontext": plain.get(term),
            "Erklärung mit Kontext": contextual.get(term),
        }
        for term in terms
    ]
    frame = pd.DataFrame(rows)
    if not contextual and "Erklärung mit Kontext" in frame:
        frame.drop(columns="Erklärung mit Kontext", inplace=True)
    return frame


def sanitize_spreadsheet_value(value: object) -> object:
    """Neutralize strings interpreted as formulas by spreadsheet applications."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def make_export_data(frame: pd.DataFrame) -> tuple[bytes, bytes]:
    """Create formula-safe Excel and CSV payloads."""
    safe_frame = frame.map(sanitize_spreadsheet_value)
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(
        excel_buffer,
        engine="xlsxwriter",
        engine_kwargs={"options": {"strings_to_formulas": False}},
    ) as writer:
        safe_frame.to_excel(writer, index=False, sheet_name="Glossar")
    csv_buffer = io.StringIO()
    safe_frame.to_csv(csv_buffer, index=False)
    return excel_buffer.getvalue(), csv_buffer.getvalue().encode("utf-8")


def zurich_timestamp(now: datetime.datetime | None = None) -> str:
    """Return a daylight-saving-aware filename timestamp for Zurich."""
    current = now or datetime.datetime.now(ZoneInfo("Europe/Zurich"))
    if current.tzinfo is None:
        current = current.replace(tzinfo=ZoneInfo("Europe/Zurich"))
    else:
        current = current.astimezone(ZoneInfo("Europe/Zurich"))
    return current.strftime("%Y%m%d_%H%M")


def safe_filename_stem(value: str, fallback: str = "glossar") -> str:
    """Create a conservative download filename stem from untrusted input."""
    stem = Path(value).stem
    cleaned = re.sub(r"[^\w.-]+", "_", stem, flags=re.UNICODE).strip("._")
    return cleaned or fallback
