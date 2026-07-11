import re
from concurrent.futures import ThreadPoolExecutor

import openai
import requests
import streamlit as st
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from settings import OpenRouterSettings, SettingsError, load_openrouter_settings

from utils_prompts_glossary import (
    EXTRACT_TERMS,
    CREATE_GLOSSARY,
    CREATE_GLOSSARY_FROM_CONTEXT,
)

JINA_PREFIX = "https://r.jina.ai/"


# Schema for list of extracted terms from text
class Term(BaseModel):
    term: str


class TermList(BaseModel):
    terms: list[Term]


# Schema for glossary entries
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
def get_openrouter_runtime() -> tuple[OpenRouterSettings, OpenAI]:
    """Load settings and construct the shared OpenRouter client lazily."""
    settings = load_openrouter_settings()
    return settings, create_openrouter_client(settings)


def call_openrouter(
    prompt: str,
    response_format: type[BaseModel] | None = None,
) -> BaseModel | str | None:
    """Call OpenRouter's Chat Completions API with error handling."""
    try:
        settings, client = get_openrouter_runtime()
        request: dict[str, object] = {
            "model": settings.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": settings.max_output_tokens,
            "temperature": settings.temperature,
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

        completion = client.chat.completions.create(**request)
        content = completion.choices[0].message.content
        if not content:
            raise ValueError("OpenRouter hat eine leere Antwort zurückgegeben.")
        return (
            response_format.model_validate_json(content) if response_format else content
        )
    except SettingsError:
        st.error(
            "OpenRouter ist nicht korrekt konfiguriert. "
            "Bitte prüfe die Anwendungseinstellungen."
        )
        return None
    except (
        openai.OpenAIError,
        ValidationError,
        ValueError,
        IndexError,
        AttributeError,
    ):
        st.error(
            "OpenRouter konnte die Anfrage nicht verarbeiten. "
            "Bitte versuche es später erneut."
        )
        return None


def clean_text(text):
    """Remove unwanted markdown formatting"""
    text = re.sub(r"[*_\#]", "", text)
    text = re.sub("ß", "ss", text)
    return text.strip()


def reset_all_session_states():
    """Reset all session states"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def extract_terms_from_text(text):
    """Extract difficult terms from text"""
    prompt = EXTRACT_TERMS.format(TEXT=text)
    with st.spinner("Begriffe aus dem Text extrahieren..."):
        result_terms = call_openrouter(prompt, response_format=TermList)

    if result_terms:
        terms = [term.term for term in result_terms.terms]
        return sorted(list(set(terms)))
    return []


def create_explanations(terms, text=None):
    """Create explanations for terms with parallel API calls"""
    terms_str = "\n".join(terms)
    explanations = None
    explanations_with_context = None

    # Function to create explanations without context
    def get_explanations_without_context():
        prompt = CREATE_GLOSSARY.format(BEGRIFFE=terms_str)
        return call_openrouter(prompt, response_format=ExplanationList)

    # Function to create explanations with context
    def get_explanations_with_context():
        if not text:
            return None
        prompt = CREATE_GLOSSARY_FROM_CONTEXT.format(TEXT=text, BEGRIFFE=terms_str)
        return call_openrouter(prompt, response_format=ExplanationList)

    # Execute both API calls in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        # Submit both tasks
        future_no_context = executor.submit(get_explanations_without_context)
        future_with_context = executor.submit(get_explanations_with_context)

        # Get results
        explanations = future_no_context.result()
        explanations_with_context = future_with_context.result()

    return explanations, explanations_with_context


def convert_url_to_markdown(url):
    """Convert URL to markdown using Jina Reader API"""
    with st.spinner("Text von Webseite lesen..."):
        final_link = JINA_PREFIX + url
        response = requests.get(final_link)
        if response.status_code == 200:
            return response.text
        else:
            st.error(f"Fehler beim Abrufen der URL: {response.status_code}")
            return None
