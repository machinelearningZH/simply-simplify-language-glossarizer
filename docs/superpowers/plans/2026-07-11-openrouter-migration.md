# OpenRouter Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route all glossary model calls through configurable OpenRouter settings while preserving typed glossary responses and the existing Streamlit workflow.

**Architecture:** A focused settings module loads non-secret values from module-relative YAML and the API key from the environment or module-relative `.env`. The existing glossary module creates an OpenAI-compatible client pointed explicitly at OpenRouter and uses Chat Completions JSON Schema structured output, then validates returned JSON with the existing Pydantic models.

**Tech Stack:** Python 3.12+, `openai`, `pydantic`, `python-dotenv`, `pyyaml`, Streamlit, pytest, Ruff

## Global Constraints

- Keep `OPENROUTER_API_KEY` only in `_streamlit_glossarizer/.env`; never log or display it.
- Default the model to `google/gemini-3-flash-preview` in `_streamlit_glossarizer/config.yaml`.
- Keep the existing OpenAI-compatible Python client; do not add the OpenRouter SDK.
- Preserve glossary prompts, Streamlit page workflows, output files, parallel explanation generation, and the separate Jina Reader integration.
- Tests must not make live network, model-provider, or other external-service calls.
- Use `uv` for dependency management and Python tooling.
- Preserve the pre-existing unstaged `uv.lock` package-upgrade changes; stage only the new direct `pyyaml` dependency metadata from that file.

---

### Task 1: Typed OpenRouter Configuration

**Files:**
- Create: `_streamlit_glossarizer/settings.py`
- Create: `_streamlit_glossarizer/config.yaml`
- Create: `tests/test_settings.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`

**Interfaces:**
- Consumes: YAML file and `OPENROUTER_API_KEY` from the process environment or `.env`.
- Produces: frozen `OpenRouterSettings`, `SettingsError`, and `load_openrouter_settings(config_path: Path = CONFIG_PATH, env_path: Path = ENV_PATH) -> OpenRouterSettings`.

- [ ] **Step 1: Add the approved YAML dependency**

Run: `uv add pyyaml`

Expected: `pyyaml` appears in `[project].dependencies`, `uv.lock` is updated, and dependency resolution succeeds.

Before continuing, inspect `git diff -- uv.lock`. Keep the pre-existing package-version updates in the working tree, and later use `git add -p uv.lock` to stage only hunks that add `pyyaml` to the root project dependency metadata.

- [ ] **Step 2: Write failing configuration tests**

Create `tests/test_settings.py`:

```python
from pathlib import Path

import pytest

from _streamlit_glossarizer.settings import SettingsError, load_openrouter_settings


def write_config(path: Path, *, model: str = "provider/model") -> None:
    path.write_text(
        f"""openrouter:
  base_url: https://openrouter.ai/api/v1
  model: {model}
  temperature: 0.1
  max_output_tokens: 2048
  timeout_seconds: 30.0
  max_retries: 3
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
    assert settings.temperature == 0.1
    assert settings.max_output_tokens == 2048
    assert settings.timeout_seconds == 30.0
    assert settings.max_retries == 3
    assert "secret-key" not in repr(settings)


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


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ("temperature: -1", "temperature"),
        ("max_output_tokens: 0", "max_output_tokens"),
        ("timeout_seconds: 0", "timeout_seconds"),
        ("max_retries: -1", "max_retries"),
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
        replacement if line.strip().startswith(f"{key}:") else line
        for line in text.splitlines()
    )
    config_path.write_text(text, encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-key")

    with pytest.raises(SettingsError, match=message):
        load_openrouter_settings(config_path, tmp_path / ".env")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_settings.py -v`

Expected: FAIL during collection because `_streamlit_glossarizer.settings` does not exist.

- [ ] **Step 4: Implement the settings module and default configuration**

Create `_streamlit_glossarizer/config.yaml`:

```yaml
openrouter:
  base_url: https://openrouter.ai/api/v1
  model: google/gemini-3-flash-preview
  temperature: 0.0
  max_output_tokens: 8192
  timeout_seconds: 60.0
  max_retries: 2
```

Create `_streamlit_glossarizer/settings.py` with a frozen dataclass whose `api_key` field uses `repr=False`. Use `yaml.safe_load`, `dotenv_values`, and `os.getenv`; prefer the process environment over `.env`. Validate that `openrouter` is a mapping, `base_url` is an HTTPS URL, `model` is non-empty, `0 <= temperature <= 2`, positive integer `max_output_tokens`, positive numeric `timeout_seconds`, and non-negative integer `max_retries`. Catch `OSError`, `yaml.YAMLError`, `KeyError`, `TypeError`, and `ValueError`, and raise `SettingsError` with a field-specific message. Define:

```python
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


def load_openrouter_settings(
    config_path: Path = CONFIG_PATH,
    env_path: Path = ENV_PATH,
) -> OpenRouterSettings:
    """Load and validate OpenRouter settings without exposing credentials."""
```

- [ ] **Step 5: Run configuration tests**

Run: `uv run pytest tests/test_settings.py -v`

Expected: all tests PASS.

- [ ] **Step 6: Format, lint, and commit the configuration unit**

Run: `uv run ruff format _streamlit_glossarizer/settings.py tests/test_settings.py`

Run: `uv run ruff check _streamlit_glossarizer/settings.py tests/test_settings.py`

Expected: both commands succeed with no diagnostics.

Stage Task 1 files without absorbing the user's pre-existing lockfile updates:

```bash
git add pyproject.toml _streamlit_glossarizer/config.yaml \
  _streamlit_glossarizer/settings.py tests/test_settings.py
git add -p uv.lock
git diff --cached --check
git diff --cached -- uv.lock
git commit -m "feat(openrouter): add validated provider settings"
```

Expected before committing: the cached `uv.lock` diff contains only root-project `pyyaml` dependency metadata; package upgrades remain unstaged.

---

### Task 2: OpenRouter Chat Completions Integration

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_utils_glossary.py`
- Modify: `_streamlit_glossarizer/utils_glossary.py`

**Interfaces:**
- Consumes: `OpenRouterSettings` and the existing `TermList`/`ExplanationList` Pydantic models.
- Produces: `create_openrouter_client(settings: OpenRouterSettings) -> OpenAI` and `call_openrouter(prompt: str, response_format: type[BaseModel] | None = None) -> BaseModel | str | None`.

- [ ] **Step 1: Write failing client and structured-output tests**

Create `tests/conftest.py` to make the Streamlit script directory importable without changing production import semantics:

```python
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "_streamlit_glossarizer"
sys.path.insert(0, str(APP_DIR))
```

Create `tests/test_utils_glossary.py` using `unittest.mock.Mock` and `monkeypatch`. Cover these exact behaviors:

```python
import json
from types import SimpleNamespace
from unittest.mock import Mock

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
    monkeypatch.setattr(utils_glossary, "get_openrouter_runtime", lambda: (settings, client))

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
    monkeypatch.setattr(utils_glossary, "get_openrouter_runtime", lambda: (settings, client))

    assert utils_glossary.call_openrouter("prompt") == "Antwort"


def test_call_openrouter_reports_configuration_error_without_secret(monkeypatch):
    error = SettingsError("OPENROUTER_API_KEY fehlt")
    monkeypatch.setattr(utils_glossary, "get_openrouter_runtime", Mock(side_effect=error))
    streamlit_error = Mock()
    monkeypatch.setattr(utils_glossary.st, "error", streamlit_error)

    assert utils_glossary.call_openrouter("prompt") is None
    message = streamlit_error.call_args.args[0]
    assert "OPENROUTER_API_KEY" in message
    assert "secret-key" not in message


def test_call_openrouter_reports_provider_error(monkeypatch):
    settings = make_settings()
    client = Mock()
    client.chat.completions.create.side_effect = RuntimeError("provider unavailable")
    monkeypatch.setattr(utils_glossary, "get_openrouter_runtime", lambda: (settings, client))
    streamlit_error = Mock()
    monkeypatch.setattr(utils_glossary.st, "error", streamlit_error)

    assert utils_glossary.call_openrouter("prompt") is None
    assert "OpenRouter" in streamlit_error.call_args.args[0]
```

- [ ] **Step 2: Run integration tests to verify they fail**

Run: `uv run pytest tests/test_utils_glossary.py -v`

Expected: FAIL because `create_openrouter_client` and the new call signature/runtime do not exist.

- [ ] **Step 3: Replace the incomplete OpenRouter implementation**

In `_streamlit_glossarizer/utils_glossary.py`:

- replace `typing.List` with built-in `list` annotations;
- remove module-level `.env` loading, hard-coded model/token constants, global client construction, and the Responses API calls;
- import `OpenRouterSettings`, `SettingsError`, and `load_openrouter_settings`;
- implement `create_openrouter_client` with the explicit constructor arguments asserted above;
- implement a cached `get_openrouter_runtime() -> tuple[OpenRouterSettings, OpenAI]` that loads settings and constructs the client lazily;
- build JSON Schema format as shown below and validate with `response_format.model_validate_json(content)`;
- pass the response model positionally or as `response_format=...` from existing callers, but remove all `model_id=DEFAULT_MODEL` arguments.

Use this request structure:

```python
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
return response_format.model_validate_json(content) if response_format else content
```

Catch `SettingsError`, `openai.OpenAIError`, `pydantic.ValidationError`, `ValueError`, `IndexError`, and `AttributeError`; display a concise German Streamlit message and return `None`. Do not catch a blanket `Exception`. Adapt tests to use an `OpenAIError` subclass rather than `RuntimeError` if required by the final exception boundary.

- [ ] **Step 4: Run integration and existing tests**

Run: `uv run pytest tests/test_utils_glossary.py tests/test_settings.py -v`

Expected: all tests PASS, and no network request occurs.

- [ ] **Step 5: Format, lint, and commit the integration unit**

Run: `uv run ruff format _streamlit_glossarizer/utils_glossary.py tests/conftest.py tests/test_utils_glossary.py`

Run: `uv run ruff check _streamlit_glossarizer/utils_glossary.py tests/conftest.py tests/test_utils_glossary.py`

Expected: both commands succeed with no diagnostics.

Commit:

```bash
git add _streamlit_glossarizer/utils_glossary.py tests/conftest.py \
  tests/test_utils_glossary.py
git commit -m "feat(openrouter): route glossary calls through chat completions"
```

---

### Task 3: OpenRouter Documentation and Provider Notice

**Files:**
- Modify: `README.md`
- Modify: `_streamlit_glossarizer/home.py`

**Interfaces:**
- Consumes: the configuration and key names introduced in Task 1.
- Produces: accurate operator setup instructions and an accurate third-party processing notice.

- [ ] **Step 1: Update user-facing provider references**

In `README.md`, replace the OpenAI setup paragraph with instructions to:

1. create an OpenRouter key at `https://openrouter.ai/settings/keys`;
2. create `_streamlit_glossarizer/.env` containing `OPENROUTER_API_KEY=...`;
3. select the model and tune non-secret request settings in `_streamlit_glossarizer/config.yaml`;
4. note that the selected model must support JSON Schema structured outputs.

In `_streamlit_glossarizer/home.py`, change `(OpenAI, Jina AI uw.)` to `(OpenRouter, ausgewählte Modellanbieter, Jina AI usw.)`. Do not alter the rest of the warning or page behavior.

- [ ] **Step 2: Verify stale references are gone**

Run:

```bash
rg -n "OpenAI LLM API|OpenAI, Jina|\.env_example" README.md _streamlit_glossarizer
```

Expected: no matches.

Run:

```bash
rg -n "OPENROUTER_API_KEY|config.yaml|OpenRouter" README.md _streamlit_glossarizer
```

Expected: matches in README, settings/configuration, integration code, and the provider notice.

- [ ] **Step 3: Commit documentation changes**

```bash
git add README.md _streamlit_glossarizer/home.py
git commit -m "docs(openrouter): update provider setup and notice"
```

---

### Task 4: Full Verification

**Files:**
- Verify only; modify a scoped file only if its own check exposes a migration-related defect.

**Interfaces:**
- Consumes: all preceding task deliverables.
- Produces: evidence that the migration is formatted, lint-clean, tested, and free of accidentally committed secrets.

- [ ] **Step 1: Check formatting without rewriting unrelated files**

Run: `uv run ruff format --check _streamlit_glossarizer tests`

Expected: all checked files are already formatted.

- [ ] **Step 2: Run lint checks**

Run: `uv run ruff check _streamlit_glossarizer tests`

Expected: no diagnostics.

- [ ] **Step 3: Run the complete test suite**

Run: `uv run pytest -v`

Expected: all tests PASS with no live external requests.

- [ ] **Step 4: Inspect the final diff and secret boundary**

Run: `git status --short`

Expected: only intentional migration changes remain; pre-existing unrelated changes are identified and excluded.

Run: `git diff --check HEAD~3..HEAD`

Expected: no whitespace errors.

Run: `git ls-files _streamlit_glossarizer/.env`

Expected: no output; the real `.env` remains untracked.

- [ ] **Step 5: Report completion**

Summarize the explicit OpenRouter endpoint, configurable model/settings, mocked test coverage, verification results, and any unrelated pre-existing working-tree changes. Suggest `feat(openrouter): complete configurable provider migration` only if additional final fixes required a separate commit.
