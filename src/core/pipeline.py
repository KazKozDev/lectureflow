"""Full analysis pipeline orchestrating all processing steps."""

from copy import deepcopy
from typing import Callable

from src.core.annotator import TopicAnnotator
from src.core.postprocessor import format_as_markdown, post_process_segments
from src.core.segmenter import SemanticSegmenter
from src.core.transcript import fetch_transcript, fetch_video_metadata, get_video_id
from src.db.repository import AnalysisRepository
from src.llm.base import BaseLLMClient
from src.llm.factory import create_llm_client
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AnalysisPipeline:
    """End-to-end transcript analysis pipeline.

    Args:
        llm_client: LLM client for post-processing. Created from config if None.
        db_path: Path to SQLite database. None to disable persistence.
    """

    def __init__(
        self,
        llm_client: BaseLLMClient | None = None,
        db_path: str | None = "data/db/timecoder.db",
    ) -> None:
        self.llm_client = llm_client or create_llm_client()
        self.segmenter = SemanticSegmenter()
        self.annotator = TopicAnnotator(model=self.segmenter.model)
        self.db = AnalysisRepository(db_path) if db_path else None
        self._base_segments_cache: dict[str, list[dict]] = {}
        self._result_cache: dict[tuple[str, str, str, str, str, bool], dict] = {}

    @staticmethod
    def _get_provider_slug(client: BaseLLMClient) -> str:
        """Convert a client class name to a stable provider slug."""
        return client.__class__.__name__.removesuffix("Client").lower()

    def _resolve_cache_identity(
        self,
        provider: str | None,
        model_name: str | None,
        language: str | None,
        skip_llm: bool,
    ) -> tuple[str, str, str]:
        """Return normalized provider/model/language values for result caching."""
        resolved_provider = provider or self._get_provider_slug(self.llm_client)
        resolved_model = model_name or self.llm_client.model_name
        resolved_language = language or "Auto"
        if skip_llm:
            resolved_provider = ""
            resolved_model = ""
        return resolved_provider, resolved_model, resolved_language

    def analyze(
        self,
        youtube_url: str,
        mode: str = "detailed",
        use_cache: bool = True,
        skip_llm: bool = False,
        provider: str | None = None,
        model_name: str | None = None,
        language: str | None = None,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> dict:
        """Run full analysis on a YouTube video.

        Args:
            youtube_url: YouTube video URL.
            mode: Analysis mode (brief, detailed, exam, flashcards, quiz).
            use_cache: Whether to return cached results if available.
            skip_llm: If True, skip LLM post-processing.
            provider: Provider override.
            model_name: Model override.

        Returns:
            Dict with video_id, segments, markdown, and metadata.
        """
        video_id = get_video_id(youtube_url)
        resolved_provider, resolved_model, resolved_language = (
            self._resolve_cache_identity(provider, model_name, language, skip_llm)
        )
        cache_key = (
            video_id,
            mode,
            resolved_provider,
            resolved_model,
            resolved_language,
            skip_llm,
        )

        logger.info("Starting analysis for video: %s (mode: %s)", video_id, mode)

        def emit_progress(step: str, progress: int, message: str) -> None:
            if progress_callback:
                progress_callback(
                    {
                        "step": step,
                        "progress": max(0, min(100, progress)),
                        "message": message,
                        "video_id": video_id,
                    }
                )

        annotated = None
        fetch_new = True

        # Check cache
        if use_cache:
            exact_cached = self._result_cache.get(cache_key)
            if exact_cached:
                logger.info("Found in-memory exact analysis cache for %s (%s)", video_id, mode)
                emit_progress("cached", 100, "Loaded cached result.")
                return deepcopy(exact_cached)

            if self.db:
                cached_result = self.db.get_analysis(
                    video_id,
                    mode=mode,
                    provider=resolved_provider,
                    model_name=resolved_model,
                    language=resolved_language,
                    skip_llm=skip_llm,
                )
                if cached_result:
                    logger.info(
                        "Found persisted exact analysis cache for %s (%s). Returning without recompute.",
                        video_id,
                        mode,
                    )
                    self._result_cache[cache_key] = deepcopy(cached_result)
                    self._base_segments_cache[video_id] = deepcopy(cached_result["segments"])
                    emit_progress("cached", 100, "Loaded cached result from database.")
                    return cached_result

            if video_id in self._base_segments_cache:
                logger.info(
                    "Found in-memory base segments for %s. Skipping transcript & ML segmentation.",
                    video_id,
                )
                annotated = deepcopy(self._base_segments_cache[video_id])
                fetch_new = False
                emit_progress("base-cache", 52, "Using cached transcript structure.")
            elif self.db:
                cached = self.db.get_analysis(video_id)
                if cached and cached.get("segments"):
                    logger.info(
                        "Found cached base segments for %s. Skipping transcript & ML segmentation.",
                        video_id,
                    )
                    self._base_segments_cache[video_id] = deepcopy(cached["segments"])
                    annotated = deepcopy(cached["segments"])
                    fetch_new = False
                    emit_progress("base-cache", 52, "Using saved transcript structure.")

        if fetch_new:
            # Fetch transcript
            emit_progress("transcript", 10, "Downloading transcript...")
            raw_segments = fetch_transcript(youtube_url, progress_callback=emit_progress)

            # Semantic segmentation
            emit_progress("segmenting", 35, "Building semantic segments...")
            grouped = self.segmenter.segment(raw_segments)

            # Topic annotation
            emit_progress("annotating", 58, "Annotating segment topics...")
            annotated = self.annotator.annotate_segments(grouped)
            self._base_segments_cache[video_id] = deepcopy(annotated)

        if annotated is None:
            raise RuntimeError("Annotated segments were not generated.")

        annotated = deepcopy(annotated)
        emit_progress("preparing", 68, "Preparing final analysis...")

        # LLM post-processing
        if not skip_llm:
            client = self.llm_client
            if provider or model_name:
                from src.llm.factory import create_llm_client

                overrides = {}
                if model_name:
                    overrides["model_name"] = model_name
                try:
                    client = create_llm_client(provider=provider, **overrides)
                except Exception as e:
                    logger.warning(
                        "Failed to create custom LLM client, using default. %s", e
                    )

            try:
                emit_progress("llm", 78, "Generating AI output...")
                if mode in ["detailed", "brief", "exam", "flashcards", "quiz", "youtube_seo"]:
                    from src.core.postprocessor import generate_global_markdown

                    markdown_output = generate_global_markdown(
                        annotated, client, mode, language=language
                    )
                else:
                    annotated = post_process_segments(
                        annotated, client, mode, language=language
                    )
                    markdown_output = format_as_markdown(annotated)
            except Exception as e:
                logger.error(
                    "LLM post-processing failed for %s (mode=%s, model=%s): %s",
                    video_id,
                    mode,
                    getattr(client, "model_name", "unknown"),
                    e,
                )
                # Do NOT save broken results to DB or cache
                raise
        else:
            markdown_output = format_as_markdown(annotated)

        emit_progress("metadata", 90, "Loading video metadata...")
        metadata = fetch_video_metadata(youtube_url)

        result = {
            "video_id": video_id,
            "url": youtube_url,
            "title": metadata.get("title", video_id),
            "mode": mode,
            "provider": resolved_provider,
            "model_name": resolved_model,
            "language": resolved_language,
            "skip_llm": skip_llm,
            "segment_count": len(annotated),
            "segments": annotated,
            "markdown": markdown_output,
        }

        # Persist only successful results
        if self.db:
            emit_progress("saving", 96, "Saving analysis to library...")
            self.db.save_analysis(result)
            logger.info("Saved analysis to database")

        self._result_cache[cache_key] = deepcopy(result)
        emit_progress("done", 100, "Analysis complete.")

        return result
