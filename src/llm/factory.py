"""LLM provider factory."""

from pathlib import Path

import yaml

from src.llm.base import BaseLLMClient
from src.utils.logger import get_logger

logger = get_logger(__name__)

_PROVIDERS = {
    "ollama": "src.llm.ollama_client.OllamaClient",
    "openai": "src.llm.openai_client.OpenAIClient",
    "anthropic": "src.llm.anthropic_client.AnthropicClient",
    "groq": "src.llm.groq_client.GroqClient",
    "grok": "src.llm.grok_client.GrokClient",
}


def create_llm_client(
    provider: str | None = None,
    config_path: str | None = None,
    **overrides: object,
) -> BaseLLMClient:
    """Create an LLM client from config or explicit provider name.

    Args:
        provider: Provider name ('ollama', 'openai', 'anthropic').
            If None, reads from config.
        config_path: Path to model_config.yaml.
        **overrides: Override any config values.

    Returns:
        Configured LLM client instance.

    Raises:
        ValueError: If provider is unknown.
    """
    if config_path is None:
        config_path = str(
            Path(__file__).parent.parent.parent / "config" / "model_config.yaml"
        )

    config: dict = {}
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file) as f:
            full_config = yaml.safe_load(f)
            models_config = full_config.get("models", {})

            if provider is None:
                provider = models_config.get("default", "openai")

            config = models_config.get(provider, {})

    if provider is None:
        provider = "openai"

    config.update(overrides)

    if provider not in _PROVIDERS:
        raise ValueError(
            f"Unknown LLM provider: {provider}. "
            f"Available: {list(_PROVIDERS.keys())}"
        )

    module_path, class_name = _PROVIDERS[provider].rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    client_class = getattr(module, class_name)

    logger.info("Creating LLM client: %s (%s)", provider, config.get("model_name", ""))
    return client_class(**config)
