import os

from src.llm.openai_client import OpenAIClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GroqClient(OpenAIClient):
    """LLM client for Groq API."""

    def __init__(
        self,
        model_name: str = "llama3-8b-8192",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        api_key: str | None = None,
        base_url: str = "https://api.groq.com/openai/v1",
    ) -> None:
        key = api_key or os.getenv("GROQ_API_KEY", "")
        if not key:
            logger.warning("GROQ_API_KEY not set")

        super().__init__(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=key,
            base_url=base_url,
        )

    def get_available_models(self) -> list[str]:
        """Fetch available models from Groq."""
        try:
            models = self._client.models.list()
            chat_models = [m.id for m in models.data if "whisper" not in m.id]
            return sorted(chat_models)
        except Exception as e:
            logger.warning("Failed to fetch Groq models: %s", e)
            return []
