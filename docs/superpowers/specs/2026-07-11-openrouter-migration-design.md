# OpenRouter Migration Design

## Goal

Route all glossary LLM requests through OpenRouter instead of the OpenAI API while retaining the existing Streamlit workflow and typed response models.

## Configuration

Add `_streamlit_glossarizer/config.yaml` with operator-tunable, non-secret settings:

- OpenRouter base URL
- model identifier, defaulting to `google/gemini-3-flash-preview`
- temperature
- maximum output tokens
- request timeout
- retry count

Keep `OPENROUTER_API_KEY` in `_streamlit_glossarizer/.env`. Resolve both files relative to the application module rather than the process working directory. Validate required values and report configuration errors clearly without exposing the API key.

## API Integration

Retain the declared `openai` package as the OpenAI-compatible client for OpenRouter. Initialize it with the configured OpenRouter base URL, API key, timeout, and retry count. Send requests using OpenRouter-compatible structured output and parse the result into the existing Pydantic models. Preserve the current parallel generation of contextual and non-contextual explanations.

Provider/model failures should return a concise German Streamlit error. Logs and displayed errors must not contain credentials.

## User-Facing Changes

Update the README setup instructions to describe obtaining and configuring an OpenRouter key and the configurable model. Replace the remaining OpenAI provider reference in the Streamlit warning with OpenRouter. Do not add model controls to the application UI.

## Testing

Add focused tests that mock the OpenAI-compatible client and cover:

- configuration loading and defaults;
- explicit OpenRouter client settings;
- successful typed response parsing;
- missing-key and provider-error behavior.

Tests must not make live network or provider calls. Run Ruff formatting/checks and the test suite before completion.

## Scope

Do not change glossary prompts, page workflows, output files, or the separate Jina Reader URL-fetching integration. Do not add a new dependency without approval; use an already-declared YAML dependency if available, otherwise request approval before adding one.
