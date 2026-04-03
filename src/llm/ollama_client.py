"""Ollama LLM client."""

import requests

from src.handlers.error_handler import LLMError, retry_on_error
from src.llm.base import BaseLLMClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class OllamaClient(BaseLLMClient):
    """LLM client for Ollama local models.

    Args:
        model_name: Ollama model name (e.g. 'gemma3:12b').
        base_url: Ollama API base URL.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens in response.
    """

    def __init__(
        self,
        model_name: str = "gemma3:12b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> None:
        super().__init__(model_name, temperature, max_tokens)
        self.base_url = base_url.rstrip("/")

    @retry_on_error(max_retries=2, delay=2.0, exceptions=(LLMError,))
    def complete(self, prompt: str, **kwargs: object) -> str:
        """Generate completion via Ollama API.

        Args:
            prompt: Input prompt text.
            **kwargs: Additional parameters.

        Returns:
            Generated text.

        Raises:
            LLMError: If Ollama API call fails.
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": self.max_tokens,
                    },
                },
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "")
        except requests.RequestException as e:
            raise LLMError(f"Ollama API error: {e}") from e

    @retry_on_error(max_retries=2, delay=2.0, exceptions=(LLMError,))
    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        """Chat via Ollama API.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            **kwargs: Additional parameters.

        Returns:
            Assistant's response text.

        Raises:
            LLMError: If Ollama API call fails.
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": self.max_tokens,
                    },
                },
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()
            return result.get("message", {}).get("content", "")
        except requests.RequestException as e:
            raise LLMError(f"Ollama chat error: {e}") from e

    def get_available_models(self) -> list[str]:
        """Fetch available local models from Ollama.

        Returns:
            List of model names.
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()
            data = response.json()
            return [
                model.get("name")
                for model in data.get("models", [])
                if model.get("name")
            ]
        except Exception as e:
            logger.warning("Failed to fetch Ollama models: %s", e)
            return []
