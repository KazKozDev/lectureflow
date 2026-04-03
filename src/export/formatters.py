"""Export formatters for multiple output formats."""

import json

from src.core.transcript import format_time
from src.utils.logger import get_logger

logger = get_logger(__name__)


def to_markdown(segments: list[dict]) -> str:
    """Format segments as Markdown.

    Args:
        segments: List of segment dicts.

    Returns:
        Markdown string.
    """
    lines = []
    for seg in segments:
        start = format_time(seg["start_time"])
        end = format_time(seg["end_time"])
        topic = seg.get("improved_topic", seg.get("topic", ""))
        text = seg.get("improved_text", seg.get("text", ""))
        lines.append(f"**[{start} - {end}] {topic}**\n\n{text}\n\n---\n")
    return "\n".join(lines)


def to_json(segments: list[dict], video_id: str = "") -> str:
    """Format segments as JSON.

    Args:
        segments: List of segment dicts.
        video_id: Optional video ID for context.

    Returns:
        JSON string.
    """
    output = {
        "video_id": video_id,
        "segments": [
            {
                "start_time": seg["start_time"],
                "end_time": seg["end_time"],
                "start_formatted": format_time(seg["start_time"]),
                "end_formatted": format_time(seg["end_time"]),
                "topic": seg.get("improved_topic", seg.get("topic", "")),
                "text": seg.get("improved_text", seg.get("text", "")),
            }
            for seg in segments
        ],
    }
    return json.dumps(output, indent=2, ensure_ascii=False)


def to_youtube_description(segments: list[dict]) -> str:
    """Format segments as YouTube video description with timestamps.

    Args:
        segments: List of segment dicts.

    Returns:
        YouTube-ready description string.
    """
    lines = ["Timestamps:", ""]
    for seg in segments:
        start = format_time(seg["start_time"])
        topic = seg.get("improved_topic", seg.get("topic", ""))
        lines.append(f"{start} — {topic}")
    return "\n".join(lines)


def to_srt(segments: list[dict]) -> str:
    """Format segments as SRT subtitle file.

    Args:
        segments: List of segment dicts.

    Returns:
        SRT formatted string.
    """
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _seconds_to_srt_time(seg["start_time"])
        end = _seconds_to_srt_time(seg["end_time"])
        text = seg.get("improved_text", seg.get("text", ""))
        # SRT entries should be reasonably short
        truncated = text[:200] + "..." if len(text) > 200 else text
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(truncated)
        lines.append("")
    return "\n".join(lines)


def _seconds_to_srt_time(seconds: float) -> str:
    """Convert seconds to SRT time format (HH:MM:SS,mmm).

    Args:
        seconds: Time in seconds.

    Returns:
        SRT-formatted time string.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
