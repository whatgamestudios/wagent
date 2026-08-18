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

import requests
from langchain_core.language_models.chat_models import BaseChatModel

DEFAULT_OLLAMA_MODEL = "gemma4:31b"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"


def _ollama_model_is_pulled(model: str, base_url: str) -> bool:
    """Check the Ollama server's installed models for one matching `model`.

    Ollama tags are name:tag (default tag "latest"); a bare name like "mistral"
    should match an installed "mistral:latest".
    """
    resp = requests.get(f"{base_url}/api/tags", timeout=5)
    resp.raise_for_status()
    installed = {m["name"] for m in resp.json().get("models", [])}
    candidates = {model} if ":" in model else {model, f"{model}:latest"}
    return bool(installed & candidates)


def get_llm(provider: str | None = None, model: str | None = None) -> BaseChatModel:
    provider = (provider or os.getenv("WORCADIAN_LLM_PROVIDER") or "ollama").lower()

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        model_name = model or os.getenv("WORCADIAN_LLM_MODEL") or DEFAULT_OLLAMA_MODEL
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

        try:
            model_pulled = _ollama_model_is_pulled(model_name, base_url)
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Could not reach Ollama at {base_url} ({exc}). Is the Ollama server "
                "running? Start it with `ollama serve` or the Ollama desktop app."
            ) from exc

        if not model_pulled:
            raise RuntimeError(
                f"Ollama model '{model_name}' has not been pulled yet. Run:\n"
                f"    ollama pull {model_name}\n"
                "then try again, or pass a different --model."
            )

        return ChatOllama(model=model_name, base_url=base_url, temperature=0.4)

    if provider in ("anthropic", "claude"):
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model or os.getenv("WORCADIAN_LLM_MODEL") or DEFAULT_ANTHROPIC_MODEL,
            temperature=0.4,
        )

    raise ValueError(f"Unknown LLM provider: {provider!r} (expected 'ollama' or 'anthropic')")
