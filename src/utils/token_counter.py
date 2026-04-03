"""Token counting utilities."""

from src.utils.logger import get_logger

logger = get_logger(__name__)


class TokenCounter:
    """Utility for estimating and managing token counts.

    Uses a simple word-based estimation. For precise counting,
    install tiktoken and use model-specific tokenizers.

    Args:
        model: Model name for tokenizer selection.
    """

    CHARS_PER_TOKEN = 4  # rough average

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model
        self._tokenizer = None
        try:
            import tiktoken

            self._tokenizer = tiktoken.encoding_for_model(model)
        except (ImportError, KeyError):
            logger.debug("tiktoken not available, using char-based estimation")

    def count(self, text: str) -> int:
        """Count tokens in text.

        Args:
            text: Input text to count tokens for.

        Returns:
            Token count (exact with tiktoken, estimated otherwise).
        """
        if not text:
            return 0
        if self._tokenizer:
            return len(self._tokenizer.encode(text))
        return max(1, len(text) // self.CHARS_PER_TOKEN)

    def truncate(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token limit.

        Args:
            text: Input text.
            max_tokens: Maximum token count.

        Returns:
            Truncated text.
        """
        current = self.count(text)
        if current <= max_tokens:
            return text

        if self._tokenizer:
            tokens = self._tokenizer.encode(text)[:max_tokens]
            return self._tokenizer.decode(tokens)

        max_chars = max_tokens * self.CHARS_PER_TOKEN
        return text[:max_chars]

    def split_by_tokens(self, text: str, chunk_size: int) -> list[str]:
        """Split text into chunks of approximately chunk_size tokens.

        Args:
            text: Input text to split.
            chunk_size: Target tokens per chunk.

        Returns:
            List of text chunks.
        """
        if self.count(text) <= chunk_size:
            return [text]

        words = text.split()
        chunks = []
        current_chunk: list[str] = []
        current_count = 0

        for word in words:
            word_tokens = self.count(word)
            if current_count + word_tokens > chunk_size and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = [word]
                current_count = word_tokens
            else:
                current_chunk.append(word)
                current_count += word_tokens

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks
