"""LLM-based post-processing for transcript segments."""

import re
from pathlib import Path

import yaml

from src.core.transcript import format_time
from src.llm.base import BaseLLMClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _clean_topic(topic: str) -> str:
    """Clean topic string for Markdown formatting.

    Args:
        topic: Raw topic text.

    Returns:
        Cleaned topic string.
    """
    topic = topic.strip()
    topic = re.sub(r"[\*]+", "", topic)
    topic = re.sub(r"\s+", " ", topic)
    return topic


def _dedupe_generated_text(text: str) -> str:
    """Remove obvious adjacent duplicate words and short phrases from generated text."""
    cleaned = text.strip()
    cleaned = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b([\w-]+(?:\s+[\w-]+){1,7})\b(?:\s*[,;:—-]?\s+)\1\b",
        r"\1",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"([,.;:!?])\1+", r"\1", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _load_prompt_template(
    mode: str = "detailed", config_path: str | None = None
) -> str:
    """Load the improvement prompt template from config for a specific mode.

    Args:
        mode: The conspect mode (e.g., brief, detailed, exam, flashcards).
        config_path: Path to prompts.yaml.

    Returns:
        Prompt template string.
    """
    if config_path is None:
        config_path = str(
            Path(__file__).parent.parent.parent / "config" / "prompts.yaml"
        )

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
            modes = config.get("templates", {}).get("modes", {})
            if mode in modes:
                return modes[mode]
            return modes.get("detailed", "")
    except (FileNotFoundError, KeyError, yaml.YAMLError):
        # Fallback template
        return (
            "Please improve only the following transcript segment:\n"
            "1. Add proper punctuation and capitalization to the text\n"
            "2. Create a concise, descriptive topic title (3-5 words)\n\n"
            "Original segment:\n"
            "[{start_time} - {end_time}] {topic}\n"
            "{text}\n\n"
            "Improved segment (do not include timestamp in response, "
            "just topic and text):\n"
        )


def post_process_segments(
    segments: list[dict],
    llm_client: BaseLLMClient,
    mode: str = "detailed",
    config_path: str | None = None,
    language: str | None = None,
) -> list[dict]:
    """Improve segment text and topics using LLM based on mode.

    Args:
        segments: List of segment dicts with text, topic, start_time, end_time.
        llm_client: LLM client to use for improvement.
        mode: Analysis mode string.
        config_path: Path to prompts.yaml.

    Returns:
        Improved segments with 'improved_topic' and 'improved_text' keys.
    """
    template = _load_prompt_template(mode, config_path)
    processed: set[str] = set()

    logger.info(
        "Post-processing %d segments with %s in '%s' mode",
        len(segments),
        llm_client.get_provider_name(),
        mode,
    )

    for segment in segments:
        start_str = format_time(segment["start_time"])
        end_str = format_time(segment["end_time"])
        key = f"{start_str}-{end_str}"

        if key in processed:
            continue

        try:
            prompt = template.format(
                start_time=start_str,
                end_time=end_str,
                topic=segment.get("topic", ""),
                text=segment["text"],
            )

            if language and language.lower() not in ["auto", ""]:
                prompt += f"\n\nCRITICAL MUST DO INSTRUCTION: You MUST translate and write ALL your response text entirely in {language}."

            response = llm_client.complete(prompt)

            if response:
                parts = response.split("\n", 1)
                if len(parts) >= 2:
                    segment["improved_topic"] = _clean_topic(parts[0])
                    segment["improved_text"] = _dedupe_generated_text(parts[1])
                else:
                    segment["improved_topic"] = _clean_topic(segment.get("topic", ""))
                    segment["improved_text"] = _dedupe_generated_text(response)

                logger.info("Processed segment %s: %s", key, segment["improved_topic"])
            else:
                segment["improved_topic"] = _clean_topic(segment.get("topic", ""))
                segment["improved_text"] = _dedupe_generated_text(segment["text"])

        except Exception as e:
            logger.error("Error processing segment %s: %s", key, e)
            segment["improved_topic"] = _clean_topic(segment.get("topic", ""))
            segment["improved_text"] = _dedupe_generated_text(segment["text"])

        processed.add(key)

    return segments


def format_as_markdown(segments: list[dict]) -> str:
    """Format processed segments as Markdown.

    Args:
        segments: List of processed segment dicts.

    Returns:
        Markdown-formatted string.
    """
    result = ""
    for segment in segments:
        start = format_time(segment["start_time"])
        end = format_time(segment["end_time"])
        topic = segment.get("improved_topic", segment.get("topic", ""))
        text = segment.get("improved_text", segment.get("text", ""))
        result += f"**[{start} - {end}] {topic}**\n\n{text}\n\n---\n\n"
    return result


def generate_global_markdown(
    segments: list[dict],
    llm_client: BaseLLMClient,
    mode: str,
    config_path: str | None = None,
    language: str | None = None,
) -> str:
    """Generate a single global Markdown document from all segments."""
    if config_path is None:
        config_path = str(
            Path(__file__).parent.parent.parent / "config" / "prompts.yaml"
        )

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
            template = config.get("templates", {}).get("global_modes", {}).get(mode, "")
            if not template:
                template = "Summarize the entire video:\n{text}"
    except Exception:
        template = "Summarize the entire video:\n{text}"

    # Combine text
    full_text = []
    for s in segments:
        start = format_time(s["start_time"])
        topic = s.get("topic", "")
        text = s.get("text", "")
        full_text.append(f"[{start}] {topic}\n{text}")

    combined = "\n\n".join(full_text)

    logger.info(
        "Generating global markdown for mode '%s' with %d segments", mode, len(segments)
    )

    try:
        prompt = template.format(text=combined)

        if language and language.lower() not in ["auto", ""]:
            prompt += f"\n\nCRITICAL MUST DO INSTRUCTION: You MUST translate and write ALL your generated Output entirely in {language} (all headings, bullet points, concepts, QA, etc)."

        response = llm_client.complete(prompt)
        if not response:
            raise RuntimeError("LLM returned empty response")
        return _dedupe_generated_text(response)
    except Exception as e:
        logger.error("Error generating global markdown: %s", e)
        raise
