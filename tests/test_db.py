"""Tests for database repository."""

from src.db.repository import AnalysisRepository


class TestAnalysisRepository:
    """Tests for SQLite persistence."""

    def test_save_and_get(self, temp_db):
        repo = AnalysisRepository(temp_db)
        result = {
            "video_id": "test123",
            "url": "https://youtube.com/watch?v=test123",
            "segment_count": 2,
            "markdown": "**test**",
            "segments": [
                {
                    "start_time": 0.0,
                    "end_time": 10.0,
                    "text": "First segment",
                    "topic": "intro",
                    "improved_topic": "Introduction",
                    "improved_text": "First segment improved",
                },
                {
                    "start_time": 10.0,
                    "end_time": 20.0,
                    "text": "Second segment",
                    "topic": "main",
                },
            ],
        }

        analysis_id = repo.save_analysis(result)
        assert analysis_id is not None

        loaded = repo.get_analysis("test123")
        assert loaded is not None
        assert loaded["video_id"] == "test123"
        assert loaded["segment_count"] == 2
        assert len(loaded["segments"]) == 2
        repo.close()

    def test_get_nonexistent(self, temp_db):
        repo = AnalysisRepository(temp_db)
        assert repo.get_analysis("nonexistent") is None
        repo.close()

    def test_list_videos(self, temp_db):
        repo = AnalysisRepository(temp_db)
        repo.save_analysis(
            {
                "video_id": "vid1",
                "url": "https://youtube.com/watch?v=vid1",
                "segment_count": 1,
                "markdown": "test",
                "segments": [{"start_time": 0, "end_time": 10, "text": "test"}],
            }
        )
        repo.save_analysis(
            {
                "video_id": "vid2",
                "url": "https://youtube.com/watch?v=vid2",
                "segment_count": 1,
                "markdown": "test2",
                "segments": [{"start_time": 0, "end_time": 10, "text": "test2"}],
            }
        )

        videos = repo.list_videos()
        assert len(videos) == 2
        repo.close()

    def test_search_segments(self, temp_db):
        repo = AnalysisRepository(temp_db)
        repo.save_analysis(
            {
                "video_id": "search_test",
                "url": "https://youtube.com/watch?v=search_test",
                "segment_count": 2,
                "markdown": "test",
                "segments": [
                    {
                        "start_time": 0,
                        "end_time": 10,
                        "text": "machine learning basics",
                    },
                    {"start_time": 10, "end_time": 20, "text": "cooking recipes"},
                ],
            }
        )

        results = repo.search_segments("machine learning")
        assert len(results) == 1
        assert "machine learning" in results[0]["text"]

        results = repo.search_segments("nonexistent query")
        assert len(results) == 0
        repo.close()

    def test_delete_video(self, temp_db):
        repo = AnalysisRepository(temp_db)
        repo.save_analysis(
            {
                "video_id": "to_delete",
                "url": "https://youtube.com/watch?v=to_delete",
                "segment_count": 1,
                "markdown": "test",
                "segments": [{"start_time": 0, "end_time": 10, "text": "test"}],
            }
        )

        assert repo.delete_video("to_delete") is True
        assert repo.get_analysis("to_delete") is None
        assert repo.delete_video("to_delete") is False
        repo.close()

    def test_overwrite_video(self, temp_db):
        repo = AnalysisRepository(temp_db)
        for i in range(2):
            repo.save_analysis(
                {
                    "video_id": "same_vid",
                    "url": "https://youtube.com/watch?v=same_vid",
                    "segment_count": 1,
                    "markdown": f"version {i}",
                    "segments": [{"start_time": 0, "end_time": 10, "text": f"v{i}"}],
                }
            )

        # Both analyses exist, one is returned
        result = repo.get_analysis("same_vid")
        assert result is not None
        assert result["video_id"] == "same_vid"
        assert result["markdown"] in ("version 0", "version 1")

        # Video appears only once in list
        videos = repo.list_videos()
        assert len(videos) == 1
        repo.close()
