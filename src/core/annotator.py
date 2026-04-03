"""Topic annotation using KeyBERT and summarization fallbacks."""

import nltk
from keybert import KeyBERT
from sentence_transformers import SentenceTransformer

from src.core.transcript import clean_transcript
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Ensure NLTK data is available
for resource, name in [
    ("tokenizers/punkt", "punkt"),
    ("corpora/stopwords", "stopwords"),
]:
    try:
        nltk.data.find(resource)
    except LookupError:
        nltk.download(name, quiet=True)


class TopicAnnotator:
    """Extract topic labels from text segments using KeyBERT.

    Args:
        model: SentenceTransformer model instance or model name.
    """

    def __init__(self, model: SentenceTransformer | str = "all-MiniLM-L6-v2") -> None:
        if isinstance(model, str):
            model = SentenceTransformer(model, device="cpu")
        self.kw_model = KeyBERT(model=model)

    def annotate(self, text: str) -> str:
        """Get topic annotation for a text segment.

        Tries KeyBERT keywords first, falls back to first sentence.

        Args:
            text: Input text to annotate.

        Returns:
            Topic string (keywords or sentence excerpt).
        """
        if not text.strip():
            return "Topic unavailable"

        cleaned = clean_transcript(text)
        if not cleaned:
            return "Topic unavailable"

        # Try KeyBERT
        try:
            keywords = self.kw_model.extract_keywords(
                cleaned,
                keyphrase_ngram_range=(1, 3),
                stop_words="english",
                top_n=5,
                diversity=0.7,
            )
            keywords.sort(key=lambda x: x[1], reverse=True)
            top = keywords[:3]
            if top:
                return ", ".join(kw[0] for kw in top)
        except Exception as e:
            logger.warning("KeyBERT extraction failed: %s", e)

        # Fallback: first sentence
        try:
            sentences = nltk.sent_tokenize(cleaned)
            if sentences:
                first = sentences[0]
                return first[:50] + ("..." if len(first) > 50 else "")
        except Exception:
            pass

        return "Topic unavailable"

    def annotate_segments(self, segments: list[dict]) -> list[dict]:
        """Add topic annotations to segment dicts.

        Args:
            segments: List of segment dicts with 'text' key.

        Returns:
            Same segments with 'topic' key added.
        """
        for segment in segments:
            segment["topic"] = self.annotate(segment["text"])
            logger.debug(
                "Annotated segment %.0f-%.0f: %s",
                segment["start_time"],
                segment["end_time"],
                segment["topic"],
            )
        return segments
