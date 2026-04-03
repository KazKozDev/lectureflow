"""CRUD operations for analysis persistence."""

import re
import threading
from typing import Any

from src.core.transcript import fetch_video_metadata
from src.db.models import get_connection
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AnalysisRepository:
    """Repository for storing and retrieving video analyses.

    Args:
        db_path: Path to SQLite database file.
    """

    def __init__(self, db_path: str = "data/db/timecoder.db") -> None:
        self.db_path = db_path
        self._conn = get_connection(db_path)
        self._lock = threading.RLock()

    @staticmethod
    def _normalize_cache_value(value: Any) -> str:
        """Normalize cache key fields for consistent SQLite comparisons."""
        if value is None:
            return ""
        return str(value)

    def save_analysis(self, result: dict[str, Any]) -> int:
        """Save analysis results to database.

        Args:
            result: Analysis result dict with video_id, url, segments, markdown.

        Returns:
            Analysis ID.
        """
        with self._lock:
            video_id = result["video_id"]
            url = result.get("url", "")
            title = result.get("title", "")

            # Upsert video
            self._conn.execute(
                """INSERT INTO videos (video_id, url, title) VALUES (?, ?, ?)
                   ON CONFLICT(video_id) DO UPDATE SET
                       url=excluded.url,
                       title=COALESCE(NULLIF(excluded.title, ''), videos.title),
                       updated_at=CURRENT_TIMESTAMP""",
                (video_id, url, title),
            )

            # Insert analysis
            cursor = self._conn.execute(
                """INSERT INTO analyses
                   (video_id, mode, provider, model_name, language, skip_llm, segment_count, markdown)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    video_id,
                    self._normalize_cache_value(result.get("mode", "detailed")),
                    self._normalize_cache_value(result.get("provider")),
                    self._normalize_cache_value(result.get("model_name")),
                    self._normalize_cache_value(result.get("language")),
                    1 if result.get("skip_llm") else 0,
                    result.get("segment_count", 0),
                    result.get("markdown", ""),
                ),
            )
            analysis_id = cursor.lastrowid

            # Insert segments
            for i, seg in enumerate(result.get("segments", [])):
                self._conn.execute(
                    """INSERT INTO segments
                       (analysis_id, start_time, end_time, text, topic,
                        improved_topic, improved_text, segment_order)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        analysis_id,
                        seg.get("start_time", 0),
                        seg.get("end_time", 0),
                        seg.get("text", ""),
                        seg.get("topic"),
                        seg.get("improved_topic"),
                        seg.get("improved_text"),
                        i,
                    ),
                )

            self._conn.commit()
        logger.info("Saved analysis %d for video %s", analysis_id, video_id)
        return analysis_id  # type: ignore[return-value]

    def get_analysis(
        self,
        video_id: str,
        *,
        mode: str | None = None,
        provider: str | None = None,
        model_name: str | None = None,
        language: str | None = None,
        skip_llm: bool | None = None,
    ) -> dict[str, Any] | None:
        """Get the latest analysis for a video.

        Args:
            video_id: YouTube video ID.

        Returns:
            Analysis result dict, or None if not found.
        """
        with self._lock:
            query = [
                """SELECT a.id, a.video_id, a.mode, a.provider, a.model_name, a.language,
                          a.skip_llm, a.segment_count, a.markdown, a.created_at, v.url, v.title
                   FROM analyses a
                   JOIN videos v ON a.video_id = v.video_id
                   WHERE a.video_id = ?"""
            ]
            params: list[Any] = [video_id]

            if mode is not None:
                query.append("AND COALESCE(a.mode, '') = ?")
                params.append(self._normalize_cache_value(mode))
            if provider is not None:
                query.append("AND COALESCE(a.provider, '') = ?")
                params.append(self._normalize_cache_value(provider))
            if model_name is not None:
                query.append("AND COALESCE(a.model_name, '') = ?")
                params.append(self._normalize_cache_value(model_name))
            if language is not None:
                query.append("AND COALESCE(a.language, '') = ?")
                params.append(self._normalize_cache_value(language))
            if skip_llm is not None:
                query.append("AND COALESCE(a.skip_llm, 0) = ?")
                params.append(1 if skip_llm else 0)

            query.append("ORDER BY a.created_at DESC LIMIT 1")
            row = self._conn.execute(" ".join(query), tuple(params)).fetchone()

            if not row:
                return None

            segments = self._conn.execute(
                """SELECT start_time, end_time, text, topic,
                          improved_topic, improved_text, segment_order
                   FROM segments
                   WHERE analysis_id = ?
                   ORDER BY segment_order""",
                (row["id"],),
            ).fetchall()

        return {
            "video_id": row["video_id"],
            "url": row["url"],
            "title": row["title"],
            "mode": row["mode"],
            "provider": row["provider"],
            "model_name": row["model_name"],
            "language": row["language"],
            "skip_llm": bool(row["skip_llm"]),
            "segment_count": row["segment_count"],
            "markdown": row["markdown"],
            "created_at": row["created_at"],
            "segments": [dict(s) for s in segments],
        }

    def list_videos(self, limit: int = 50) -> list[dict[str, Any]]:
        """List all analyzed videos.

        Args:
            limit: Maximum number of results.

        Returns:
            List of video summary dicts.
        """
        with self._lock:
            rows = self._conn.execute(
                """SELECT v.video_id, v.url, v.title, v.created_at,
                          COUNT(a.id) as analysis_count
                   FROM videos v
                   LEFT JOIN analyses a ON v.video_id = a.video_id
                   GROUP BY v.video_id
                   ORDER BY v.updated_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            videos = [dict(r) for r in rows]

            updated = False
            for video in videos:
                current_title = (video.get("title") or "").strip()
                if current_title and current_title != video["video_id"]:
                    continue
                metadata = fetch_video_metadata(video.get("url", ""))
                resolved_title = (metadata.get("title") or "").strip()
                if not resolved_title:
                    continue
                video["title"] = resolved_title
                self._conn.execute(
                    "UPDATE videos SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE video_id = ?",
                    (resolved_title, video["video_id"]),
                )
                updated = True

            if updated:
                self._conn.commit()

        return videos

    @staticmethod
    def _extract_keywords(text: str, limit: int = 30) -> set[str]:
        stopwords = {
            "about", "after", "again", "also", "and", "are", "because", "been", "before",
            "between", "both", "but", "can", "could", "does", "each", "even", "from",
            "have", "into", "just", "more", "most", "much", "only", "other", "over",
            "same", "should", "some", "than", "that", "their", "them", "then", "there",
            "these", "they", "this", "those", "through", "under", "very", "what", "when",
            "where", "which", "while", "with", "would", "your", "youtube", "video",
        }
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", (text or "").lower())
        ranked: dict[str, int] = {}
        for token in tokens:
            if token in stopwords:
                continue
            ranked[token] = ranked.get(token, 0) + 1
        return {
            token
            for token, _count in sorted(
                ranked.items(), key=lambda item: (-item[1], item[0])
            )[:limit]
        }

    @staticmethod
    def _tokenize_query(text: str) -> list[str]:
        tokens = re.findall(r"[A-Za-zА-Яа-яЁё0-9_-]{2,}", (text or "").lower())
        seen: set[str] = set()
        ordered: list[str] = []
        for token in tokens:
            if token in seen:
                continue
            seen.add(token)
            ordered.append(token)
        return ordered

    def get_recommendations(
        self, video_id: str, limit: int = 6
    ) -> list[dict[str, Any]]:
        """Return similar videos from the local library based on keyword overlap.

        If overlap is too weak, fill the list with recent library videos so the UI
        never stays empty while the user already has analyzed content.
        """
        base = self.get_analysis(video_id)
        if not base:
            return []

        base_keywords = self._extract_keywords(
            " ".join(
                [
                    base.get("markdown", ""),
                    *(seg.get("topic", "") for seg in base.get("segments", [])),
                    *(seg.get("text", "") for seg in base.get("segments", [])),
                ]
            )
        )
        if not base_keywords:
            return []

        candidates = [video for video in self.list_videos(limit=100) if video["video_id"] != video_id]
        scored: list[dict[str, Any]] = []
        for candidate in candidates:
            analysis = self.get_analysis(candidate["video_id"])
            if not analysis:
                continue
            candidate_keywords = self._extract_keywords(
                " ".join(
                    [
                        analysis.get("markdown", ""),
                        *(seg.get("topic", "") for seg in analysis.get("segments", [])),
                        *(seg.get("text", "") for seg in analysis.get("segments", [])),
                    ]
                )
            )
            overlap = base_keywords.intersection(candidate_keywords)
            if not overlap:
                continue
            score = len(overlap)
            scored.append(
                {
                    "video_id": candidate["video_id"],
                    "url": candidate.get("url", ""),
                    "title": candidate.get("title") or candidate["video_id"],
                    "thumbnail_url": f"https://i.ytimg.com/vi/{candidate['video_id']}/hqdefault.jpg",
                    "score": score,
                    "shared_keywords": sorted(list(overlap))[:6],
                }
            )

        scored.sort(key=lambda item: (-item["score"], item["title"]))
        results = scored[:limit]

        if len(results) >= limit:
            return results

        used_ids = {item["video_id"] for item in results}
        fallback_items: list[dict[str, Any]] = []
        for candidate in candidates:
            if candidate["video_id"] in used_ids:
                continue
            fallback_items.append(
                {
                    "video_id": candidate["video_id"],
                    "url": candidate.get("url", ""),
                    "title": candidate.get("title") or candidate["video_id"],
                    "thumbnail_url": f"https://i.ytimg.com/vi/{candidate['video_id']}/hqdefault.jpg",
                    "score": 0,
                    "shared_keywords": [],
                    "fallback": True,
                }
            )
            if len(results) + len(fallback_items) >= limit:
                break

        return results + fallback_items

    def search_segments(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Hybrid search across all segments and video titles.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of matching segment dicts with video context.
        """
        normalized_query = (query or "").strip()
        if not normalized_query:
            return []
        lowered_query = normalized_query.lower()
        tokens = self._tokenize_query(normalized_query)
        safe_query = normalized_query.replace('"', '""')
        token_match_query = " OR ".join(f'"{token}"' for token in tokens) if tokens else ""

        candidate_map: dict[int, dict[str, Any]] = {}

        def add_candidate(row: Any, score: float) -> None:
            segment_id = int(row["id"])
            existing = candidate_map.get(segment_id)
            base = dict(row)
            base["score"] = max(float(existing["score"]), score) if existing else score
            candidate_map[segment_id] = base

        with self._lock:
            if safe_query:
                try:
                    rows = self._conn.execute(
                        """SELECT s.*, a.video_id, v.url, v.title
                           FROM segments_fts f
                           JOIN segments s ON f.rowid = s.id
                           JOIN analyses a ON s.analysis_id = a.id
                           JOIN videos v ON a.video_id = v.video_id
                           WHERE segments_fts MATCH ?
                           ORDER BY bm25(segments_fts)
                           LIMIT ?""",
                        (f'"{safe_query}"', max(limit * 5, 25)),
                    ).fetchall()
                    for rank, row in enumerate(rows):
                        add_candidate(row, 160 - rank)
                except Exception as e:
                    logger.warning("Exact FTS search failed: %s", e)

            if token_match_query:
                try:
                    rows = self._conn.execute(
                        """SELECT s.*, a.video_id, v.url, v.title
                           FROM segments_fts f
                           JOIN segments s ON f.rowid = s.id
                           JOIN analyses a ON s.analysis_id = a.id
                           JOIN videos v ON a.video_id = v.video_id
                           WHERE segments_fts MATCH ?
                           ORDER BY bm25(segments_fts)
                           LIMIT ?""",
                        (token_match_query, max(limit * 8, 40)),
                    ).fetchall()
                    for rank, row in enumerate(rows):
                        add_candidate(row, 110 - (rank * 0.5))
                except Exception as e:
                    logger.warning("Token FTS search failed: %s", e)

            try:
                rows = self._conn.execute(
                    """SELECT s.*, a.video_id, v.url, v.title
                       FROM segments s
                       JOIN analyses a ON s.analysis_id = a.id
                       JOIN videos v ON a.video_id = v.video_id
                       WHERE COALESCE(v.title, '') LIKE ?
                          OR s.text LIKE ? OR s.improved_text LIKE ?
                          OR COALESCE(s.topic, '') LIKE ? OR COALESCE(s.improved_topic, '') LIKE ?
                       ORDER BY a.created_at DESC, s.start_time ASC
                       LIMIT ?""",
                    (f"%{normalized_query}%",) * 5 + (max(limit * 12, 80),),
                ).fetchall()
            except Exception as e:
                logger.warning("LIKE search failed: %s", e)
                rows = []

        for row in rows:
            hay_title = str(row.get("title") or "").lower()
            hay_topic = f"{row.get('topic') or ''} {row.get('improved_topic') or ''}".lower()
            hay_text = f"{row.get('text') or ''} {row.get('improved_text') or ''}".lower()

            score = 0.0
            if lowered_query in hay_title:
                score += 18
            if lowered_query in hay_topic:
                score += 14
            if lowered_query in hay_text:
                score += 10

            for token in tokens:
                if token in hay_title:
                    score += 4.0
                if token in hay_topic:
                    score += 3.0
                if token in hay_text:
                    score += 1.5

            if score > 0:
                add_candidate(row, score)

        ranked = sorted(
            candidate_map.values(),
            key=lambda item: (-float(item["score"]), item["video_id"], item["start_time"]),
        )
        return ranked[:limit]

    def get_latest_analysis(self) -> dict[str, Any] | None:
        """Return the most recently updated video's latest analysis."""
        with self._lock:
            row = self._conn.execute(
                """SELECT v.video_id
                   FROM videos v
                   ORDER BY v.updated_at DESC
                   LIMIT 1"""
            ).fetchone()
        if not row:
            return None
        return self.get_analysis(row["video_id"])

    def delete_video(self, video_id: str) -> bool:
        """Delete a video and all its analyses.

        Args:
            video_id: YouTube video ID.

        Returns:
            True if video was found and deleted.
        """
        # Get analysis IDs first
        with self._lock:
            analysis_ids = self._conn.execute(
                "SELECT id FROM analyses WHERE video_id = ?", (video_id,)
            ).fetchall()

            for row in analysis_ids:
                self._conn.execute(
                    "DELETE FROM segments WHERE analysis_id = ?", (row["id"],)
                )

            self._conn.execute("DELETE FROM analyses WHERE video_id = ?", (video_id,))
            cursor = self._conn.execute(
                "DELETE FROM videos WHERE video_id = ?", (video_id,)
            )
            self._conn.commit()

        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Deleted video %s and all analyses", video_id)
        return deleted

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.close()
