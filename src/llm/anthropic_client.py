"""Anthropic Claude LLM client."""

import os

from src.handlers.error_handler import LLMError, retry_on_error
from src.llm.base import BaseLLMClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AnthropicClient(BaseLLMClient):
    """LLM client for Anthropic Claude API.

    Args:
        model_name: Claude model name.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens in response.
        api_key: Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
    """

    def __init__(
        self,
        model_name: str = "claude-sonnet-4-20250514",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        api_key: str | None = None,
    ) -> None:
        super().__init__(model_name, temperature, max_tokens)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set")

        try:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError as e:
            raise LLMError(
                "anthropic package not installed: pip install anthropic"
            ) from e

    @retry_on_error(max_retries=3, delay=1.0, exceptions=(LLMError,))
    def complete(self, prompt: str, **kwargs: object) -> str:
        """Generate completion via Claude API.

        Args:
            prompt: Input prompt text.
            **kwargs: Additional parameters.

        Returns:
            Generated text.

        Raises:
            LLMError: If Anthropic API call fails.
        """
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    @retry_on_error(max_retries=3, delay=1.0, exceptions=(LLMError,))
    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        """Chat via Claude API.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            **kwargs: Additional parameters.

        Returns:
            Assistant's response text.

        Raises:
            LLMError: If Anthropic API call fails.
        """
        try:
            response = self._client.messages.create(
                model=self.model_name,
                max_tokens=self.max_tokens,
                messages=messages,  # type: ignore[arg-type]
                temperature=self.temperature,
            )
            return response.content[0].text
        except Exception as e:
            raise LLMError(f"Anthropic API error: {e}") from e

    def get_available_models(self) -> list[str]:
        """Fetch available models from Anthropic API.

        Returns:
            List of model names.
        """
        try:
            models = self._client.models.list()
            return [m.id for m in models.data if "claude" in m.id.lower()]
        except Exception as e:
            logger.warning("Failed to fetch Anthropic models: %s", e)
            return []
