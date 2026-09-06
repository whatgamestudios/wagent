"""Build a LangChain chat model, with automatic fallback across up to five configured models.

Configuration is a numbered list of (model, API key) slots:

    MODEL_NAME_1 / MODEL_API_KEY_1
    MODEL_NAME_2 / MODEL_API_KEY_2
    MODEL_NAME_3 / MODEL_API_KEY_3
    MODEL_NAME_4 / MODEL_API_KEY_4
    MODEL_NAME_5 / MODEL_API_KEY_5

Each MODEL_NAME_N is a model string for LangChain's `init_chat_model()`
(https://python.langchain.com/docs/how_to/chat_models_universal_init/):
either "<provider>:<model>" (e.g. "anthropic:claude-sonnet-5",
"openai:gpt-4o-mini", "google_genai:gemini-2.0-flash",
"groq:llama-3.3-70b-versatile", "ollama:llama3.1") or, for well-known model
families, just the bare model id with the provider inferred from its name.
An explicit "provider:" prefix is recommended since it's unambiguous.

Slots are tried in numeric order. The first slot with MODEL_NAME_N set is the
primary model; any further configured slots are attached as automatic
LangChain fallbacks via `with_fallbacks()` — if a call to an earlier model
raises, LangChain retries it against the next one. MODEL_API_KEY_N is
optional (e.g. a local Ollama model needs no key); when set, it's passed to
the model as its `api_key`. A local Ollama model additionally picks up
OLLAMA_BASE_URL (default "http://localhost:11434") if that's set.

At least one slot must be configured (or --model passed explicitly).
"""

from __future__ import annotations

import os

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

NUM_SLOTS = 5


def _provider_of(model_name: str, explicit_provider: str | None) -> str | None:
    if explicit_provider:
        return explicit_provider
    if ":" in model_name:
        return model_name.split(":", 1)[0]
    return None


def _build(model_name: str, api_key: str | None, explicit_provider: str | None = None) -> BaseChatModel:
    kwargs: dict = {"temperature": 0.4}
    if api_key:
        kwargs["api_key"] = api_key
    if explicit_provider:
        kwargs["model_provider"] = explicit_provider

    if _provider_of(model_name, explicit_provider) == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url

    return init_chat_model(model_name, **kwargs)


def _slot(n: int) -> tuple[str | None, str | None]:
    return os.getenv(f"MODEL_NAME_{n}"), os.getenv(f"MODEL_API_KEY_{n}")


def get_llm(provider: str | None = None, model: str | None = None) -> BaseChatModel:
    """Return a chat model.

    If `model` is given explicitly (the CLI's --model flag), that single
    model is built directly — `provider` (the CLI's --provider flag), if
    given, is passed through as an explicit model_provider for it. Otherwise
    a fallback chain is built from the MODEL_NAME_1..5 / MODEL_API_KEY_1..5
    env vars, in slot order.
    """
    if model:
        return _build(model, api_key=None, explicit_provider=provider)

    llms = []
    for n in range(1, NUM_SLOTS + 1):
        model_name, api_key = _slot(n)
        if model_name:
            llms.append(_build(model_name, api_key))

    if not llms:
        raise RuntimeError(
            "No LLM model is configured. Set MODEL_NAME_1 (and optionally "
            "MODEL_API_KEY_1) through MODEL_NAME_5 / MODEL_API_KEY_5, or pass "
            "--model explicitly."
        )

    primary, fallbacks = llms[0], llms[1:]
    return primary.with_fallbacks(fallbacks) if fallbacks else primary
