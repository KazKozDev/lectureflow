"""OpenAI LLM client."""

import os

from src.handlers.error_handler import LLMError, retry_on_error
from src.llm.base import BaseLLMClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class OpenAIClient(BaseLLMClient):
    """LLM client for OpenAI API.

    Args:
        model_name: OpenAI model name.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens in response.
        api_key: OpenAI API key. Falls back to OPENAI_API_KEY env var.
    """

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(model_name, temperature, max_tokens)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set")

        try:
            from openai import OpenAI

            kwargs = {}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(api_key=self.api_key, **kwargs)
        except ImportError as e:
            raise LLMError("openai package not installed: pip install openai") from e

    @retry_on_error(max_retries=3, delay=1.0, exceptions=(LLMError,))
    def complete(self, prompt: str, **kwargs: object) -> str:
        """Generate completion via OpenAI API.

        Args:
            prompt: Input prompt text.
            **kwargs: Additional parameters.

        Returns:
            Generated text.

        Raises:
            LLMError: If OpenAI API call fails.
        """
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    @retry_on_error(max_retries=3, delay=1.0, exceptions=(LLMError,))
    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        """Chat via OpenAI API.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            **kwargs: Additional parameters.

        Returns:
            Assistant's response text.

        Raises:
            LLMError: If OpenAI API call fails.
        """
        try:
            params: dict = {
                "model": self.model_name,
                "messages": messages,
            }
            # Newer models (o-series, gpt-5+) require max_completion_tokens
            # and some don't support the temperature parameter.
            _new_model = (
                self.model_name.startswith(("o1", "o3", "o4"))
                or self.model_name.startswith("gpt-5")
            )
            if _new_model:
                params["max_completion_tokens"] = self.max_tokens
            else:
                params["max_tokens"] = self.max_tokens
                params["temperature"] = self.temperature
            response = self._client.chat.completions.create(**params)
            return response.choices[0].message.content or ""
        except Exception as e:
            raise LLMError(f"OpenAI API error: {e}") from e

    def get_available_models(self) -> list[str]:
        """Fetch available models from OpenAI API.

        Filters the list to include relevant chat models.

        Returns:
            List of model names.
        """
        try:
            models = self._client.models.list()
            # Dynamic unrestricted load from API
            # Substrings that indicate a model does NOT support
            # the /v1/chat/completions endpoint.
            _EXCLUDE = (
                "-pro",          # o1-pro, o3-pro — Responses API only
                "-deep-research",  # reasoning-only models
                "gpt-image",     # image generation
                "-transcribe",   # audio transcription
                "-codex",        # code-only models
                "-search-",      # search-augmented previews
                "-instruct",     # completions-only (v1/completions)
                "chatgpt-image", # image generation alias
            )
            chat_models = [
                m.id
                for m in models.data
                if not any(ex in m.id for ex in _EXCLUDE)
                and "vision" not in m.id
                and "audio" not in m.id
                and "realtime" not in m.id
                and "dall-e" not in m.id
                and "tts" not in m.id
                and "whisper" not in m.id
                and "embedding" not in m.id
                and "babbage" not in m.id
                and "davinci" not in m.id
                and (
                    "gpt" in m.id
                    or "o1" in m.id
                    or "o3" in m.id
                    or "o4" in m.id
                )
            ]
            return sorted(chat_models, reverse=True)
        except Exception as e:
            logger.warning("Failed to fetch OpenAI models: %s", e)
            return []
