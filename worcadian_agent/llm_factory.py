"""Build a configured LangChain chat model — local Ollama or remote Claude.

Selection order for provider/model: explicit function argument, then environment
variable, then a hardcoded default (local Ollama, so the pipeline runs out of the
box without any API key).

Env vars:
    WORCADIAN_LLM_PROVIDER   "ollama" (default) or "anthropic"
    WORCADIAN_LLM_MODEL      overrides the default model for the chosen provider
    OLLAMA_BASE_URL          default "http://localhost:11434"
    ANTHROPIC_API_KEY        required when provider is "anthropic"
"""

from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel

DEFAULT_OLLAMA_MODEL = "llama3.1"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"


def get_llm(provider: str | None = None, model: str | None = None) -> BaseChatModel:
    provider = (provider or os.getenv("WORCADIAN_LLM_PROVIDER") or "ollama").lower()

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model or os.getenv("WORCADIAN_LLM_MODEL") or DEFAULT_OLLAMA_MODEL,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=0.4,
        )

    if provider in ("anthropic", "claude"):
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model or os.getenv("WORCADIAN_LLM_MODEL") or DEFAULT_ANTHROPIC_MODEL,
            temperature=0.4,
        )

    raise ValueError(f"Unknown LLM provider: {provider!r} (expected 'ollama' or 'anthropic')")
