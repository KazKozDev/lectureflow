"""Tests for LLM factory and clients."""

import pytest

from src.llm.base import BaseLLMClient
from src.llm.factory import create_llm_client


class TestBaseLLMClient:
    """Tests for abstract base class."""

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseLLMClient("model")

    def test_mock_client(self, mock_llm):
        assert mock_llm.model_name == "mock-model"
        result = mock_llm.complete("test")
        assert "Mock" in result

    def test_mock_with_custom_responses(self, mock_llm):
        mock_llm.set_responses(["First", "Second"])
        assert mock_llm.complete("a") == "First"
        assert mock_llm.complete("b") == "Second"

    def test_provider_name(self, mock_llm):
        assert mock_llm.get_provider_name() == "MockLLMClient"


class TestFactory:
    """Tests for LLM factory."""

    def test_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_llm_client(provider="nonexistent")

    def test_ollama_creation(self):
        client = create_llm_client(
            provider="ollama",
            model_name="test-model",
            base_url="http://localhost:11434",
        )
        assert client.model_name == "test-model"
        assert isinstance(client, BaseLLMClient)
