import os

from src.llm.openai_client import OpenAIClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GrokClient(OpenAIClient):
    """LLM client for Grok (xAI) API."""

    def __init__(
        self,
        model_name: str = "grok-2-latest",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        api_key: str | None = None,
        base_url: str = "https://api.x.ai/v1",
    ) -> None:
        key = api_key or os.getenv("XAI_API_KEY", "")
        if not key:
            logger.warning("XAI_API_KEY not set")

        super().__init__(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=key,
            base_url=base_url,
        )

    def get_available_models(self) -> list[str]:
        """Fetch available models from xAI."""
        try:
            models = self._client.models.list()
            chat_models = [m.id for m in models.data]
            return sorted(chat_models)
        except Exception as e:
            logger.warning("Failed to fetch Grok models: %s", e)
            return []
