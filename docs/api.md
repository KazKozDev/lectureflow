# API Reference

Base URL: `http://localhost:8000`

## Analysis

### POST /api/analyze

Analyze a single YouTube video (blocking).

**Request:**
```json
{
  "url": "https://youtube.com/watch?v=VIDEO_ID",
  "mode": "detailed",
  "skip_llm": false,
  "use_cache": true,
  "provider": "openai",
  "model_name": "gpt-4o-mini",
  "language": "en"
}
```

**Modes:** `detailed`, `brief`, `exam`, `flashcards`, `quiz`, `youtube_seo`

All fields except `url` are optional. `provider` and `model_name` override the defaults from config.

**Response:**
```json
{
  "status": "success",
  "data": {
    "video_id": "...",
    "segment_count": 12,
    "markdown": "...",
    "segments": [
      {
        "start_time": 0.0,
        "end_time": 120.5,
        "topic": "Introduction",
        "text": "..."
      }
    ]
  }
}
```

### POST /api/analyze/stream

Analyze a video with real-time streaming progress (NDJSON).

Same request body as `/api/analyze`. Returns `application/x-ndjson` with events:

- `{"type": "progress", ...}` — pipeline step updates
- `{"type": "result", "data": {...}}` — final result
- `{"type": "error", "detail": "..."}` — if analysis fails

### POST /api/analyze/batch

Analyze all videos in a YouTube playlist (NDJSON streaming).

**Request:**
```json
{
  "url": "https://youtube.com/playlist?list=PLAYLIST_ID",
  "mode": "detailed"
}
```

## Library

### GET /api/videos

List all analyzed videos.

### GET /api/videos/{video_id}

Get full analysis for a specific video.

### DELETE /api/videos/{video_id}

Delete a video and all its analyses.

### POST /api/search

Full-text search across all segments.

**Request:**
```json
{
  "query": "machine learning",
  "limit": 20
}
```

## Recommendations

### GET /api/videos/{video_id}/recommendations?limit=6

Get similar videos from the local library (cosine similarity).

### GET /api/videos/{video_id}/youtube-recommendations?limit=6

Get YouTube search recommendations based on video topics. Requires `YOUTUBE_API_KEY`.

## Chat

### POST /api/chat

RAG-based Q&A over the video library.

**Request:**
```json
{
  "query": "What did the video say about neural networks?",
  "limit": 20,
  "provider": "openai",
  "model_name": "gpt-4o-mini"
}
```

## Export

### GET /api/export/{video_id}?format=json

Export video analysis. Formats: `json`, `markdown`, `srt`, `youtube`.

## Settings

### GET /api/settings/keys

Get currently configured API keys.

### POST /api/settings/keys

Update API keys at runtime.

**Request:**
```json
{
  "openai": "sk-...",
  "anthropic": "sk-ant-..."
}
```

### GET /api/models

List available models from all configured providers.

## Health

### GET /health

Returns `{"status": "healthy", "version": "0.2.0"}`.
