"""Shared test fixtures."""

import os
import tempfile

import pytest

from src.llm.base import BaseLLMClient


class MockLLMClient(BaseLLMClient):
    """Mock LLM client for testing."""

    def __init__(self) -> None:
        super().__init__("mock-model", 0.7, 4096)
        self.responses: list[str] = []
        self._call_count = 0

    def set_responses(self, responses: list[str]) -> None:
        self.responses = responses
        self._call_count = 0

    def complete(self, prompt: str, **kwargs: object) -> str:
        if self.responses:
            idx = min(self._call_count, len(self.responses) - 1)
            self._call_count += 1
            return self.responses[idx]
        return "Mock Topic\n\nMock improved text content."

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        return self.complete(messages[-1]["content"])

    def get_available_models(self) -> list[str]:
        return ["mock-model-1", "mock-model-2"]


@pytest.fixture
def mock_llm():
    """Provide a mock LLM client."""
    return MockLLMClient()


@pytest.fixture
def sample_segments():
    """Provide sample transcript segments."""
    return [
        ("Hello world this is a test segment", 0.0, 5.0),
        ("We are discussing machine learning today", 5.0, 4.0),
        ("Neural networks are very powerful", 9.0, 3.0),
        ("Deep learning has many applications", 12.0, 5.0),
        ("Computer vision is one application", 17.0, 4.0),
        ("Natural language processing is another", 21.0, 3.0),
        ("Transformers changed the field", 24.0, 4.0),
        ("Attention mechanism is the key innovation", 28.0, 5.0),
        ("BERT was a breakthrough model", 33.0, 3.0),
        ("GPT models generate text", 36.0, 4.0),
        ("Language models keep improving", 40.0, 3.0),
        ("The future of AI is exciting", 43.0, 5.0),
    ]


@pytest.fixture
def sample_grouped_segments():
    """Provide sample grouped segment dicts."""
    return [
        {
            "start_time": 0.0,
            "end_time": 12.0,
            "text": "Hello world this is a test. We discuss ML. Neural nets.",
            "topic": "machine learning, neural networks",
            "segment_count": 3,
        },
        {
            "start_time": 12.0,
            "end_time": 28.0,
            "text": "Deep learning applications. Vision. NLP. Transformers.",
            "topic": "deep learning, applications",
            "segment_count": 4,
        },
        {
            "start_time": 28.0,
            "end_time": 48.0,
            "text": "Attention is key. BERT breakthrough. GPT generates. Future.",
            "topic": "attention, language models",
            "segment_count": 5,
        },
    ]


@pytest.fixture
def temp_db():
    """Provide a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test.db")


@pytest.fixture
def temp_cache_dir():
    """Provide a temporary cache directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir
