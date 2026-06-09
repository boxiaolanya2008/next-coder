# Custom provider for any OpenAI-compatible endpoint.
# Works with OpenRouter, DeepSeek, Ollama, etc.

from __future__ import annotations

from nextcli.llm.openai_provider import OpenAIProvider


class CustomProvider(OpenAIProvider):
    """An OpenAIProvider pointed at a user-supplied base URL."""

    name = "custom"

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        # need a base url and model to talk to custom endpoints
        if not base_url:
            raise ValueError("CustomProvider requires a non-empty base_url")
        if not model:
            raise ValueError("CustomProvider requires a non-empty model id")
        super().__init__(api_key=api_key, model=model)
        self.base_url = base_url
        # create the client with the custom base url
        from openai import AsyncOpenAI  # type: ignore

        self._client = AsyncOpenAI(api_key=api_key or "EMPTY", base_url=base_url)
