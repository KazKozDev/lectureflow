"""FastAPI application for Timecoder API."""

import asyncio
import json
import os

# PyTorch MPS Fallback: Apple Silicon (M1/M2/M3) throws an error if an operation is missing.
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.core.pipeline import AnalysisPipeline
from src.core.transcript import fetch_youtube_recommendations
from src.utils.logger import get_logger, setup_logging

load_dotenv()
setup_logging()

logger = get_logger(__name__)

pipeline: AnalysisPipeline | None = None
pipeline_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize pipeline on startup."""
    logger.info("Timecoder API started")
    yield
    if pipeline and pipeline.db:
        pipeline.db.close()
    logger.info("Timecoder API stopped")


async def get_pipeline() -> AnalysisPipeline:
    """Lazily initialize the heavy analysis pipeline."""
    global pipeline
    if pipeline is not None:
        return pipeline

    async with pipeline_lock:
        if pipeline is None:
            pipeline = await asyncio.to_thread(AnalysisPipeline)
            logger.info("Analysis pipeline initialized")

    return pipeline


app = FastAPI(
    title="Timecoder API",
    description="YouTube transcript analyzer with AI-powered semantic segmentation",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount public directory for static UI if it exists
public_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "public"
)
if os.path.exists(public_dir):
    app.mount("/ui", StaticFiles(directory=public_dir, html=True), name="public")


class AnalyzeRequest(BaseModel):
    """Request body for video analysis."""

    url: str
    mode: str = "detailed"
    skip_llm: bool = False
    use_cache: bool = True
    provider: str | None = None
    model_name: str | None = None
    language: str | None = None


class ChatRequest(BaseModel):
    query: str
    limit: int = 20
    provider: str | None = None
    model_name: str | None = None
    language: str | None = None


class SearchRequest(BaseModel):
    """Request body for search."""

    query: str
    limit: int = 20


class APIKeysUpdate(BaseModel):
    openai: str | None = None
    anthropic: str | None = None
    groq: str | None = None
    grok: str | None = None
    youtube: str | None = None


@app.post("/api/analyze")
async def analyze_video(request: AnalyzeRequest):
    """Analyze a YouTube video transcript.

    Returns segmented, annotated, and optionally LLM-improved results.
    """
    active_pipeline = await get_pipeline()

    try:
        result = await asyncio.to_thread(
            active_pipeline.analyze,
            request.url,
            mode=request.mode,
            use_cache=request.use_cache,
            skip_llm=request.skip_llm,
            provider=request.provider,
            model_name=request.model_name,
            language=request.language,
        )
        response_data: dict = {
            "video_id": result["video_id"],
            "segment_count": result["segment_count"],
            "markdown": result["markdown"],
            "segments": [
                {
                    "start_time": s["start_time"],
                    "end_time": s["end_time"],
                    "topic": s.get("improved_topic", s.get("topic", "")),
                    "text": s.get("improved_text", s.get("text", "")),
                }
                for s in result["segments"]
            ],
        }

        md = result.get("markdown", "")
        if md.startswith("Error:") or md.startswith("Failed to generate"):
            response_data["warning"] = md
            response_data["markdown"] = ""

        return {
            "status": "success",
            "data": response_data,
        }
    except Exception as e:
        logger.error("Analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/analyze/stream")
async def analyze_video_stream(request: AnalyzeRequest):
    """Analyze a YouTube video and stream real pipeline progress as NDJSON."""
    active_pipeline = await get_pipeline()

    async def event_generator():
        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        def progress_callback(event: dict) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "progress", **event})

        def worker() -> None:
            try:
                result = active_pipeline.analyze(
                    request.url,
                    mode=request.mode,
                    use_cache=request.use_cache,
                    skip_llm=request.skip_llm,
                    provider=request.provider,
                    model_name=request.model_name,
                    language=request.language,
                    progress_callback=progress_callback,
                )
                response_data: dict = {
                    "video_id": result["video_id"],
                    "title": result.get("title", result["video_id"]),
                    "segment_count": result["segment_count"],
                    "markdown": result["markdown"],
                    "segments": [
                        {
                            "start_time": s["start_time"],
                            "end_time": s["end_time"],
                            "topic": s.get("improved_topic", s.get("topic", "")),
                            "text": s.get("improved_text", s.get("text", "")),
                        }
                        for s in result["segments"]
                    ],
                }
                md = result.get("markdown", "")
                if md.startswith("Error:") or md.startswith("Failed to generate"):
                    response_data["warning"] = md
                    response_data["markdown"] = ""
                loop.call_soon_threadsafe(
                    queue.put_nowait, {"type": "result", "data": response_data}
                )
            except Exception as e:
                logger.error("Streaming analysis failed: %s", e)
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "detail": str(e)})
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        loop = asyncio.get_running_loop()
        task = asyncio.create_task(asyncio.to_thread(worker))

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield json.dumps(event) + "\n"
        finally:
            await task

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


@app.post("/api/analyze/batch")
async def analyze_playlist(request: AnalyzeRequest):
    """Analyze a YouTube playlist using Server-Sent Events (NDJSON streaming)."""
    active_pipeline = await get_pipeline()

    from src.core.transcript import get_playlist_urls

    urls = get_playlist_urls(request.url)
    if not urls:
        raise HTTPException(status_code=400, detail="No videos found in playlist")

    async def event_generator():
        total = len(urls)
        yield json.dumps(
            {"type": "info", "message": f"Found {total} videos in playlist."}
        ) + "\n"

        for i, url in enumerate(urls, 1):
            yield json.dumps(
                {"type": "progress", "index": i, "total": total, "url": url}
            ) + "\n"
            try:
                result = await asyncio.to_thread(
                    active_pipeline.analyze,
                    url,
                    mode=request.mode,
                    use_cache=request.use_cache,
                    skip_llm=request.skip_llm,
                    provider=request.provider,
                    model_name=request.model_name,
                    language=request.language,
                )
                yield json.dumps(
                    {"type": "success", "url": url, "video_id": result.get("video_id")}
                ) + "\n"
            except Exception as e:
                logger.error("Error analyzing playlist video %s: %s", url, e)
                yield json.dumps(
                    {"type": "error", "url": url, "message": str(e)}
                ) + "\n"

        yield json.dumps(
            {"type": "done", "message": "Playlist processing complete"}
        ) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


@app.get("/api/videos")
async def list_videos():
    """List all analyzed videos."""
    active_pipeline = await get_pipeline()
    if not active_pipeline.db:
        raise HTTPException(status_code=503, detail="Database not available")

    videos = active_pipeline.db.list_videos()
    return {"status": "success", "data": videos}


@app.get("/api/videos/{video_id}")
async def get_video(video_id: str):
    """Get analysis results for a specific video."""
    active_pipeline = await get_pipeline()
    if not active_pipeline.db:
        raise HTTPException(status_code=503, detail="Database not available")

    result = active_pipeline.db.get_analysis(video_id)
    if not result:
        raise HTTPException(status_code=404, detail="Video not found")

    return {"status": "success", "data": result}


@app.get("/api/videos/{video_id}/recommendations")
async def get_video_recommendations(video_id: str, limit: int = 6):
    """Get similar videos from the local analyzed library."""
    active_pipeline = await get_pipeline()
    if not active_pipeline.db:
        raise HTTPException(status_code=503, detail="Database not available")

    results = active_pipeline.db.get_recommendations(video_id, limit)
    return {"status": "success", "data": results, "count": len(results)}


@app.get("/api/videos/{video_id}/youtube-recommendations")
async def get_youtube_video_recommendations(video_id: str, limit: int = 6):
    """Get search-based YouTube recommendations via Google API."""
    active_pipeline = await get_pipeline()
    if not active_pipeline.db:
        raise HTTPException(status_code=503, detail="Database not available")

    base = active_pipeline.db.get_analysis(video_id)
    if not base:
        raise HTTPException(status_code=404, detail="Video not found")

    title = (base.get("title") or "").strip()
    segment_topics = " ".join(
        str(seg.get("topic") or "") for seg in (base.get("segments") or [])[:4]
    ).strip()
    query = " ".join(part for part in [title, segment_topics] if part).strip()
    if not query:
        query = video_id

    results = fetch_youtube_recommendations(query, exclude_video_id=video_id, limit=limit)
    return {
        "status": "success",
        "data": results,
        "count": len(results),
        "query": query,
        "configured": bool(os.getenv("YOUTUBE_API_KEY", "").strip()),
    }


@app.post("/api/search")
async def search_segments(request: SearchRequest):
    """Search across all analyzed video segments."""
    active_pipeline = await get_pipeline()
    if not active_pipeline.db:
        raise HTTPException(status_code=503, detail="Database not available")

    results = active_pipeline.db.search_segments(request.query, request.limit)
    return {"status": "success", "data": results, "count": len(results)}


@app.delete("/api/videos/{video_id}")
async def delete_video(video_id: str):
    """Delete a video and all its analyses."""
    active_pipeline = await get_pipeline()
    if not active_pipeline.db:
        raise HTTPException(status_code=503, detail="Database not available")

    deleted = active_pipeline.db.delete_video(video_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Video not found")

    return {"status": "success", "message": f"Video {video_id} deleted"}


@app.get("/api/export/{video_id}")
async def export_video(video_id: str, format: str = "json"):
    """Export video segments in a specific format (json, markdown, srt, youtube)."""
    active_pipeline = await get_pipeline()
    if not active_pipeline.db:
        raise HTTPException(status_code=503, detail="Database not available")

    result = active_pipeline.db.get_analysis(video_id)
    if not result:
        raise HTTPException(status_code=404, detail="Video not found")

    from fastapi.responses import PlainTextResponse

    from src.export.formatters import (
        to_srt,
        to_youtube_description,
    )

    if format == "markdown":
        return PlainTextResponse(result["markdown"])
    elif format == "srt":
        srt_data = to_srt(result["segments"])
        return PlainTextResponse(srt_data)
    elif format == "youtube":
        yt_data = to_youtube_description(result["segments"])
        return PlainTextResponse(yt_data)

    return {"status": "success", "data": result}


# ChatRequest moved above


@app.post("/api/chat")
async def chat_with_agent(request: ChatRequest):
    """Ask a question to the video library agent."""
    active_pipeline = await get_pipeline()
    if not active_pipeline.db or not active_pipeline.llm_client:
        raise HTTPException(status_code=503, detail="Pipeline not available")

    from src.core.agent import VideoAgent

    agent = VideoAgent(active_pipeline.db, active_pipeline.llm_client)

    try:
        answer = agent.chat(
            request.query,
            request.limit,
            request.provider,
            request.model_name,
            request.language,
        )
        return {"status": "success", "answer": answer}
    except Exception as e:
        logger.error("Agent chat failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/settings/keys")
def get_api_keys():
    """Get currently configured API keys."""
    return {
        "status": "success",
        "data": {
            "openai": os.getenv("OPENAI_API_KEY", ""),
            "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
            "groq": os.getenv("GROQ_API_KEY", ""),
            "grok": os.getenv("XAI_API_KEY", ""),
            "youtube": os.getenv("YOUTUBE_API_KEY", ""),
        },
    }


@app.post("/api/settings/keys")
def update_api_keys(keys: APIKeysUpdate):
    """Update API keys in .env and environment."""
    from dotenv import set_key

    # Ensure file exists
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
    )
    if not os.path.exists(env_path):
        with open(env_path, "w") as f:
            f.write("")

    if keys.openai is not None:
        set_key(env_path, "OPENAI_API_KEY", keys.openai)
        os.environ["OPENAI_API_KEY"] = keys.openai
    if keys.anthropic is not None:
        set_key(env_path, "ANTHROPIC_API_KEY", keys.anthropic)
        os.environ["ANTHROPIC_API_KEY"] = keys.anthropic
    if keys.groq is not None:
        set_key(env_path, "GROQ_API_KEY", keys.groq)
        os.environ["GROQ_API_KEY"] = keys.groq
    if keys.grok is not None:
        set_key(env_path, "XAI_API_KEY", keys.grok)
        os.environ["XAI_API_KEY"] = keys.grok
    if keys.youtube is not None:
        set_key(env_path, "YOUTUBE_API_KEY", keys.youtube)
        os.environ["YOUTUBE_API_KEY"] = keys.youtube

    return {"status": "success", "message": "API Keys updated successfully"}


@app.get("/api/models")
async def get_models():
    """Get list of available LLM models from all configured providers."""

    config_path = (
        Path(__file__).resolve().parent.parent.parent / "config" / "model_config.yaml"
    )
    provider_env_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "groq": "GROQ_API_KEY",
        "grok": "XAI_API_KEY",
    }

    all_models: dict[str, list[str]] = {}
    config: dict = {}
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}

    models_config = config.get("models", {})

    ollama_model = models_config.get("ollama", {}).get("model_name", "gemma3:12b")
    try:
        from src.llm.factory import create_llm_client

        ollama_client = create_llm_client(provider="ollama")
        fetched = ollama_client.get_available_models()
        all_models["ollama"] = fetched or [ollama_model]
    except Exception as e:
        logger.warning("Failed to fetch models for ollama: %s", e)
        all_models["ollama"] = [ollama_model]

    for provider, env_var in provider_env_map.items():
        configured_model = models_config.get(provider, {}).get("model_name")
        if not os.getenv(env_var):
            all_models[provider] = [configured_model] if configured_model else []
            continue

        try:
            from src.llm.factory import create_llm_client

            client = create_llm_client(provider=provider)
            fetched = client.get_available_models()
            all_models[provider] = fetched or ([configured_model] if configured_model else [])
        except Exception as e:
            logger.warning("Failed to fetch models for %s: %s", provider, e)
            all_models[provider] = [configured_model] if configured_model else []

    return {
        "status": "success",
        "data": all_models,
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.2.0"}


@app.get("/")
async def root_redirect():
    """Redirect to the Web UI."""
    return RedirectResponse(url="/ui/index.html")
