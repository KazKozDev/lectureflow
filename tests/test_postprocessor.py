"""Tests for post-processor."""

from src.core.postprocessor import format_as_markdown, post_process_segments


class TestPostProcessor:
    """Tests for LLM-based post processing."""

    def test_post_process_with_mock(self, mock_llm, sample_grouped_segments):
        mock_llm.set_responses(
            [
                "AI Fundamentals\n\nIntroduction to machine learning and neural networks.",
                "Applications Overview\n\nDeep learning in computer vision and NLP.",
                "Modern Architectures\n\nAttention mechanisms and language models.",
            ]
        )

        result = post_process_segments(sample_grouped_segments, mock_llm)
        assert len(result) == 3
        assert result[0]["improved_topic"] == "AI Fundamentals"
        assert "Introduction" in result[0]["improved_text"]

    def test_post_process_handles_error(self, mock_llm, sample_grouped_segments):
        """Should fall back to original text on LLM failure."""

        class FailingLLM:
            def complete(self, prompt, **kwargs):
                raise Exception("LLM failed")

            def get_provider_name(self):
                return "FailingLLM"

        result = post_process_segments(sample_grouped_segments, FailingLLM())
        assert len(result) == 3
        for seg in result:
            assert seg["improved_text"] == seg["text"]

    def test_format_as_markdown(self, sample_grouped_segments):
        md = format_as_markdown(sample_grouped_segments)
        assert "**[00:00 - 00:12]" in md
        assert "---" in md
        assert len(md) > 0

    def test_skips_duplicate_segments(self, mock_llm):
        """Should skip segments with same time key."""
        segments = [
            {"start_time": 0.0, "end_time": 10.0, "text": "test", "topic": "t"},
            {"start_time": 0.0, "end_time": 10.0, "text": "test", "topic": "t"},
        ]
        result = post_process_segments(segments, mock_llm)
        # Second should reuse first's processing
        assert len(result) == 2
