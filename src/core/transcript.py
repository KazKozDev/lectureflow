"""YouTube transcript fetching and preprocessing."""

from collections.abc import Callable, Iterable
import os
import re
import shutil

import requests
from youtube_transcript_api import YouTubeTranscriptApi

from src.handlers.error_handler import TranscriptError
from src.utils.logger import get_logger

logger = get_logger(__name__)

WHISPER_FALLBACK_ERROR_NAMES = {
    "CouldNotRetrieveTranscript",
    "IpBlocked",
    "NoTranscriptAvailable",
    "NoTranscriptFound",
    "RequestBlocked",
    "TranscriptsDisabled",
    "VideoUnavailable",
}

WHISPER_FALLBACK_ERROR_PATTERNS = (
    "could not retrieve a transcript",
    "no element found",
    "no transcript available",
    "no transcript found",
    "parseerror",
    "subtitles are disabled",
    "transcripts are disabled",
    "transcriptsdisabled",
)

PREFERRED_TRANSCRIPT_LANGUAGES = (
    ["en", "en-US", "en-GB"],
    ["ru", "ru-RU", "en", "en-US", "en-GB"],
    ["es", "es-ES", "en", "en-US", "en-GB"],
)


def _get_yt_dlp_base_opts() -> dict:
    """Base yt-dlp options with JS runtime support when available."""
    opts: dict = {
        "quiet": True,
        "nocheckcertificate": True,
    }
    node_path = shutil.which("node")
    if node_path:
        opts["js_runtimes"] = {"node": {"path": node_path}}
    return opts


def get_video_id(youtube_url: str) -> str:
    """Extract video ID from a YouTube URL.

    Args:
        youtube_url: Full YouTube URL or short link.

    Returns:
        11-character video ID.

    Raises:
        TranscriptError: If URL is invalid or no video ID found.
    """
    youtube_regex = (
        r"(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/"
        r"|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
    )
    match = re.search(youtube_regex, youtube_url)
    if match:
        return match.group(1)
    raise TranscriptError(f"Invalid YouTube URL: {youtube_url}")


def fetch_video_metadata(youtube_url: str) -> dict[str, str]:
    """Fetch lightweight YouTube metadata without downloading media."""
    video_id = get_video_id(youtube_url)
    thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

    try:
        import yt_dlp

        ydl_opts = {
            **_get_yt_dlp_base_opts(),
            "skip_download": True,
            "extract_flat": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False) or {}
        return {
            "title": str(info.get("title") or video_id),
            "thumbnail_url": str(info.get("thumbnail") or thumbnail_url),
        }
    except Exception as e:
        logger.warning("Failed to fetch video metadata for %s: %s", youtube_url, e)
        return {"title": video_id, "thumbnail_url": thumbnail_url}


def fetch_youtube_recommendations(query: str, exclude_video_id: str = "", limit: int = 6) -> list[dict[str, str]]:
    """Fetch YouTube search-based recommendations via Google YouTube Data API."""
    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not api_key or not query.strip():
        return []

    try:
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "type": "video",
                "maxResults": max(1, min(int(limit) * 2, 12)),
                "q": query.strip(),
                "key": api_key,
                "safeSearch": "none",
                "regionCode": "US",
                "relevanceLanguage": "en",
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json() or {}
    except Exception as e:
        logger.warning("Failed to fetch YouTube recommendations for '%s': %s", query, e)
        return []

    items = payload.get("items") or []
    recommendations: list[dict[str, str]] = []
    for item in items:
        video_id = (
            ((item.get("id") or {}).get("videoId"))
            if isinstance(item.get("id"), dict)
            else ""
        )
        snippet = item.get("snippet") or {}
        if not video_id or video_id == exclude_video_id:
            continue
        thumbnails = snippet.get("thumbnails") or {}
        thumb = (
            (thumbnails.get("high") or {}).get("url")
            or (thumbnails.get("medium") or {}).get("url")
            or (thumbnails.get("default") or {}).get("url")
            or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        )
        recommendations.append(
            {
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": str(snippet.get("title") or video_id),
                "thumbnail_url": str(thumb),
                "channel_title": str(snippet.get("channelTitle") or ""),
                "published_at": str(snippet.get("publishedAt") or ""),
            }
        )
        if len(recommendations) >= limit:
            break

    return recommendations


def format_time(seconds: float) -> str:
    """Convert seconds to MM:SS format.

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted time string.
    """
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


def clean_transcript(text: str) -> str:
    """Clean transcript text by removing annotations and filler words.

    Args:
        text: Raw transcript text.

    Returns:
        Cleaned text.
    """
    text = re.sub(r"\[.*?\]", "", text)
    fillers = r"\b(uh|um|you know|like|right|okay|so|well)\b"
    text = re.sub(fillers, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\b([\w-]+(?:\s+[\w-]+){1,7})\b(?:\s*[,;:—-]?\s+)\1\b",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"([,.;:!?])\1+", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def preprocess_segments(
    segments: list[tuple[str, float, float]],
    min_segment_length: int = 5,
) -> list[tuple[str, float, float]]:
    """Merge short segments into neighboring ones.

    Args:
        segments: List of (text, start_time, duration) tuples.
        min_segment_length: Minimum character length for a segment.

    Returns:
        Merged list of segments.
    """
    merged: list[tuple[str, float, float]] = []
    current_text = ""
    current_start: float | None = None
    current_duration = 0.0

    for text, start, duration in segments:
        text_clean = clean_transcript(text)
        if len(text_clean) < min_segment_length and current_text:
            current_text += " " + text_clean
            current_duration += duration
        else:
            if current_text and current_start is not None:
                merged.append((current_text, current_start, current_duration))
            current_text = text_clean
            current_start = start
            current_duration = duration

    if current_text and current_start is not None:
        merged.append((current_text, current_start, current_duration))

    return merged


def should_use_whisper_fallback(error: Exception) -> bool:
    """Return True when a YouTube transcript failure should trigger Whisper."""
    error_name = type(error).__name__
    error_msg = str(error).lower()

    if error_name in WHISPER_FALLBACK_ERROR_NAMES:
        return True

    return any(pattern in error_msg for pattern in WHISPER_FALLBACK_ERROR_PATTERNS)


def _list_transcripts(video_id: str):
    """Return the available transcript list across youtube-transcript-api versions."""
    api = YouTubeTranscriptApi()
    if hasattr(api, "list"):
        return api.list(video_id)
    return YouTubeTranscriptApi.list_transcripts(video_id)


def _to_segment_tuples(transcript_data: Iterable[dict]) -> list[tuple[str, float, float]]:
    """Normalize transcript API payload into internal segment tuples."""
    segments = [
        (item["text"], item["start"], item["duration"])
        for item in transcript_data
        if item["text"].strip()
    ]
    if not segments:
        raise TranscriptError("No valid transcript segments found.")
    return preprocess_segments(segments)


def _build_transcript_candidates(transcript_list) -> list:
    """Rank transcripts by desirability before falling back to Whisper."""
    candidates = []
    seen_keys = set()

    for language_codes in PREFERRED_TRANSCRIPT_LANGUAGES:
        for finder_name in (
            "find_manually_created_transcript",
            "find_transcript",
            "find_generated_transcript",
        ):
            finder = getattr(transcript_list, finder_name, None)
            if not finder:
                continue
            try:
                transcript = finder(language_codes)
            except Exception:
                continue

            key = (
                getattr(transcript, "language_code", None),
                getattr(transcript, "is_generated", None),
            )
            if key not in seen_keys:
                seen_keys.add(key)
                candidates.append(transcript)

    for transcript in transcript_list:
        key = (
            getattr(transcript, "language_code", None),
            getattr(transcript, "is_generated", None),
        )
        if key not in seen_keys:
            seen_keys.add(key)
            candidates.append(transcript)

    return candidates


def fetch_with_whisper(
    youtube_url: str,
    progress_callback: Callable[[str, int, str], None] | None = None,
) -> list[tuple[str, float, float]]:
    """Fallback: Download audio via yt-dlp and transcribe using Whisper.

    Args:
        youtube_url: YouTube video URL.

    Returns:
        List of (text, start_time, duration) tuples.
    """
    import os
    import tempfile

    try:
        import whisper
        import yt_dlp
    except ImportError as e:
        raise TranscriptError(
            "Whisper & yt-dlp are required for fallback. Please run: pip install openai-whisper yt-dlp"
        ) from e

    logger.info(
        "Falling back to Whisper to transcribe audio. This might take a while..."
    )
    if progress_callback:
        progress_callback(
            "whisper-fallback",
            16,
            "Transcript unavailable. Switching to Whisper audio transcription...",
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.m4a")

        # 1. Download audio via yt-dlp
        ydl_opts = {
            **_get_yt_dlp_base_opts(),
            "format": "m4a/bestaudio/best",
            "outtmpl": audio_path,
        }
        if progress_callback:
            progress_callback(
                "whisper-download",
                22,
                "Downloading audio for Whisper transcription...",
            )
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])

        if not os.path.exists(audio_path):
            raise TranscriptError("Failed to download audio for Whisper transcription.")

        # 2. Transcribe with Whisper
        device = "cpu"
        fp16 = False
        try:
            import torch

            if torch.backends.mps.is_available():
                device = "mps"
        except Exception:
            device = "cpu"

        logger.info("Audio downloaded. Loading Whisper model ('base') on %s...", device)
        if progress_callback:
            progress_callback(
                "whisper-model",
                30,
                f"Loading Whisper model on {device.upper()}...",
            )

        try:
            model = whisper.load_model("base", device=device)
            logger.info("Transcribing audio on %s...", device)
            if progress_callback:
                progress_callback(
                    "whisper-transcribe",
                    42,
                    f"Transcribing audio with Whisper on {device.upper()}... This can take a few minutes.",
                )
            result = model.transcribe(audio_path, fp16=fp16, language=None, task="transcribe")
        except RuntimeError as e:
            if device != "cpu" and "SparseMPS" in str(e):
                logger.warning("MPS sparse tensors not supported, falling back to CPU")
                device = "cpu"
                if progress_callback:
                    progress_callback("whisper-model", 30, "Reloading Whisper model on CPU...")
                model = whisper.load_model("base", device=device)
                if progress_callback:
                    progress_callback("whisper-transcribe", 42, "Transcribing audio on CPU...")
                result = model.transcribe(audio_path, fp16=False, language=None, task="transcribe")
            else:
                raise

        segments = []
        for segment in result.get("segments", []):
            start = segment["start"]
            duration = segment["end"] - segment["start"]
            text = segment["text"]
            segments.append((text, start, duration))

        if not segments:
            raise TranscriptError("Whisper could not generate any transcript.")

        logger.info("Whisper transcription complete: %d segments", len(segments))

        # We can also preprocess to merge tiny Whisper segments if needed
        return preprocess_segments(segments)


def fetch_transcript(
    youtube_url: str,
    progress_callback: Callable[[str, int, str], None] | None = None,
) -> list[tuple[str, float, float]]:
    """Fetch and preprocess transcript from YouTube.

    Args:
        youtube_url: YouTube video URL.

    Returns:
        List of (text, start_time, duration) tuples after preprocessing.

    Raises:
        TranscriptError: If transcript cannot be fetched.
    """
    try:
        video_id = get_video_id(youtube_url)
        transcript_list = _list_transcripts(video_id)
        candidates = _build_transcript_candidates(transcript_list)
        if not candidates:
            raise TranscriptError("No transcript available for this video.")

        last_error: Exception | None = None
        for transcript in candidates:
            try:
                logger.info(
                    "Trying transcript track: lang=%s generated=%s",
                    getattr(transcript, "language_code", "unknown"),
                    getattr(transcript, "is_generated", "unknown"),
                )
                transcript_data = transcript.fetch()
                if not transcript_data:
                    raise TranscriptError("Transcript data is empty.")

                logger.info("Fetched %d transcript segments", len(transcript_data))
                segments = _to_segment_tuples(transcript_data)
                logger.info("After preprocessing: %d segments", len(segments))
                return segments
            except TranscriptError as e:
                last_error = e
            except Exception as e:
                last_error = e
                logger.warning(
                    "Transcript track failed: lang=%s generated=%s error=%s",
                    getattr(transcript, "language_code", "unknown"),
                    getattr(transcript, "is_generated", "unknown"),
                    e,
                )

        if last_error:
            raise last_error
        raise TranscriptError("No usable transcript tracks found.")

    except TranscriptError:
        raise
    except Exception as e:
        if should_use_whisper_fallback(e):
            logger.warning(
                "YouTube API failed, triggering Whisper fallback... Error: %s",
                str(e),
            )
            return fetch_with_whisper(youtube_url, progress_callback=progress_callback)
        raise TranscriptError(f"Failed to fetch transcript: {e}") from e


def get_playlist_urls(playlist_url: str) -> list[str]:
    """Get all video URLs from a YouTube playlist.

    Args:
        playlist_url: YouTube playlist URL.

    Returns:
        List of YouTube video URLs.
    """
    import yt_dlp
    from yt_dlp.utils import DownloadError

    logger.info("Extracting playlist URLs: %s", playlist_url)
    ydl_opts = {**_get_yt_dlp_base_opts(), "extract_flat": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(playlist_url, download=False)
            if result and "entries" in result:
                urls = []
                for entry in result["entries"]:
                    if entry and entry.get("id"):
                        vid_url = f"https://www.youtube.com/watch?v={entry['id']}"
                        urls.append(vid_url)
                if urls:
                    logger.info("Found %d videos in playlist", len(urls))
                    return urls
    except DownloadError as e:
        logger.error("yt-dlp failed to extract playlist: %s", e)

    return [playlist_url]
