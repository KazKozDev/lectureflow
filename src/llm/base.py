"""Abstract base class for LLM clients."""

from abc import ABC, abstractmethod

from src.utils.logger import get_logger

logger = get_logger(__name__)


class BaseLLMClient(ABC):
    """Abstract base for all LLM providers.

    Args:
        model_name: Name of the model to use.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens in response.
    """

    def __init__(
        self,
        model_name: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> None:
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    def complete(self, prompt: str, **kwargs: object) -> str:
        """Generate a completion for the given prompt.

        Args:
            prompt: The input prompt.
            **kwargs: Additional provider-specific parameters.

        Returns:
            Generated text response.
        """

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        """Send a chat conversation and get a response.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            **kwargs: Additional provider-specific parameters.

        Returns:
            Assistant's response text.
        """

    def get_provider_name(self) -> str:
        """Return the provider name for logging."""
        return self.__class__.__name__
