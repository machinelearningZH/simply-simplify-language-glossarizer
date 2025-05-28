import streamlit as st
import requests
import re
import os
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List
from concurrent.futures import ThreadPoolExecutor

from utils_prompts_glossary import (
    EXTRACT_TERMS,
    CREATE_GLOSSARY,
    CREATE_GLOSSARY_FROM_CONTEXT,
)

load_dotenv(".env_example")

TEMPERATURE_SIMPLIFICATION = 0.5
MAX_TOKENS = 8192
JINA_PREFIX = "https://r.jina.ai/"
GPT41_mini = "gpt-4.1-mini"


# Schema for list of extracted terms from text
class Term(BaseModel):
    term: str


class TermList(BaseModel):
    terms: List[Term]


# Schema for glossary entries
class Explanation(BaseModel):
    text: str


class ExplanationElement(BaseModel):
    begriff: str
    erklaerung: Explanation


class ExplanationList(BaseModel):
    begriffe: List[ExplanationElement]


@st.cache_resource
def init_openai_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


client = init_openai_client()


def call_openai(
    prompt,
    model_id=GPT41_mini,
    temperature=TEMPERATURE_SIMPLIFICATION,
    max_tokens=MAX_TOKENS,
    response_format=None,
):
    """Call OpenAI API with error handling"""

    try:
        if response_format:
            completion = client.beta.chat.completions.parse(
                model=model_id,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "user", "content": prompt},
                ],
                response_format=response_format,
            )
            return completion.choices[0].message.parsed
        else:
            completion = client.chat.completions.create(
                model=model_id,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "user", "content": prompt},
                ],
            )
            return completion.choices[0].message.content
    except Exception as e:
        st.error(f"Fehler beim Aufruf der OpenAI API: {e}")
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
        result_terms = call_openai(prompt, model_id=GPT41_mini, response_format=TermList)

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
        return call_openai(prompt, model_id=GPT41_mini, response_format=ExplanationList)

    # Function to create explanations with context
    def get_explanations_with_context():
        if not text:
            return None
        prompt = CREATE_GLOSSARY_FROM_CONTEXT.format(TEXT=text, BEGRIFFE=terms_str)
        return call_openai(prompt, model_id=GPT41_mini, response_format=ExplanationList)

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
