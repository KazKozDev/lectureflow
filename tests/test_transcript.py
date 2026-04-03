"""Tests for transcript module."""

import pytest

from src.core.transcript import (
    _build_transcript_candidates,
    clean_transcript,
    fetch_transcript,
    format_time,
    get_video_id,
    preprocess_segments,
    should_use_whisper_fallback,
)
from src.handlers.error_handler import TranscriptError


class TestGetVideoId:
    """Tests for YouTube URL parsing."""

    def test_standard_url(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert get_video_id(url) == "dQw4w9WgXcQ"

    def test_short_url(self):
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert get_video_id(url) == "dQw4w9WgXcQ"

    def test_embed_url(self):
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        assert get_video_id(url) == "dQw4w9WgXcQ"

    def test_url_with_params(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120"
        assert get_video_id(url) == "dQw4w9WgXcQ"

    def test_invalid_url(self):
        with pytest.raises(TranscriptError):
            get_video_id("https://example.com")

    def test_empty_url(self):
        with pytest.raises(TranscriptError):
            get_video_id("")


class TestFormatTime:
    """Tests for time formatting."""

    def test_zero(self):
        assert format_time(0) == "00:00"

    def test_seconds_only(self):
        assert format_time(45) == "00:45"

    def test_minutes_and_seconds(self):
        assert format_time(125) == "02:05"

    def test_fractional(self):
        assert format_time(90.7) == "01:30"

    def test_large_value(self):
        assert format_time(3661) == "61:01"


class TestCleanTranscript:
    """Tests for transcript cleaning."""

    def test_removes_brackets(self):
        assert clean_transcript("Hello [Music] world") == "Hello world"

    def test_removes_fillers(self):
        result = clean_transcript("So uh we um started the project")
        assert "uh" not in result
        assert "um" not in result

    def test_normalizes_whitespace(self):
        assert clean_transcript("hello   world  test") == "hello world test"

    def test_empty_string(self):
        assert clean_transcript("") == ""

    def test_only_brackets(self):
        assert clean_transcript("[Music] [Applause]") == ""


class TestPreprocessSegments:
    """Tests for segment merging."""

    def test_merges_short_segments(self):
        segments = [
            ("Hello world discussion", 0.0, 5.0),
            ("ok", 5.0, 1.0),
            ("Next topic discussion here", 6.0, 5.0),
        ]
        result = preprocess_segments(segments)
        # "ok" is short, should be merged with previous
        assert len(result) == 2

    def test_keeps_normal_segments(self):
        segments = [
            ("This is a normal segment with enough text", 0.0, 5.0),
            ("Another normal segment with content", 5.0, 5.0),
        ]
        result = preprocess_segments(segments)
        assert len(result) == 2

    def test_empty_list(self):
        assert preprocess_segments([]) == []

    def test_single_segment(self):
        segments = [("Hello world test segment", 0.0, 5.0)]
        result = preprocess_segments(segments)
        assert len(result) == 1


class TestWhisperFallback:
    """Tests for transcript fallback selection."""

    def test_detects_disabled_subtitles_message(self):
        error = Exception("Subtitles are disabled for this video")
        assert should_use_whisper_fallback(error) is True

    def test_detects_transcripts_disabled_exception_name(self):
        TranscriptsDisabled = type("TranscriptsDisabled", (Exception,), {})
        error = TranscriptsDisabled("captions disabled")
        assert should_use_whisper_fallback(error) is True

    def test_fetch_transcript_falls_back_to_whisper(self, monkeypatch):
        class FakeApi:
            @staticmethod
            def list_transcripts(_video_id):
                raise Exception(
                    "Could not retrieve a transcript for the video. "
                    "Subtitles are disabled for this video"
                )

        whisper_segments = [("fallback text", 0.0, 4.0)]

        monkeypatch.setattr("src.core.transcript.get_video_id", lambda _url: "abc123")
        monkeypatch.setattr("src.core.transcript.YouTubeTranscriptApi", FakeApi)
        monkeypatch.setattr(
            "src.core.transcript.fetch_with_whisper",
            lambda _url: whisper_segments,
        )

        result = fetch_transcript("https://www.youtube.com/watch?v=abc123def45")
        assert result == whisper_segments


class TestTranscriptSelection:
    """Tests for smarter transcript retrieval before Whisper fallback."""

    def test_candidate_order_prefers_manual_then_generated(self):
        class FakeTranscript:
            def __init__(self, language_code, is_generated):
                self.language_code = language_code
                self.is_generated = is_generated

        manual_en = FakeTranscript("en", False)
        generated_en = FakeTranscript("en", True)
        generated_es = FakeTranscript("es", True)

        class FakeTranscriptList:
            def __iter__(self):
                return iter([generated_es, manual_en, generated_en])

            def find_manually_created_transcript(self, language_codes):
                if "en" in language_codes:
                    return manual_en
                raise Exception("not found")

            def find_transcript(self, language_codes):
                if "en" in language_codes:
                    return manual_en
                raise Exception("not found")

            def find_generated_transcript(self, language_codes):
                if "en" in language_codes:
                    return generated_en
                raise Exception("not found")

        candidates = _build_transcript_candidates(FakeTranscriptList())
        assert candidates[0] is manual_en
        assert candidates[1] is generated_en
        assert generated_es in candidates

    def test_fetch_transcript_tries_next_track_before_whisper(self, monkeypatch):
        class BrokenTranscript:
            language_code = "en"
            is_generated = False

            def fetch(self):
                raise Exception("temporary transcript fetch failure")

        class WorkingTranscript:
            language_code = "es"
            is_generated = True

            def fetch(self):
                return [{"text": "hola mundo", "start": 0.0, "duration": 2.0}]

        class FakeTranscriptList:
            def __iter__(self):
                return iter([BrokenTranscript(), WorkingTranscript()])

            def find_manually_created_transcript(self, _language_codes):
                return BrokenTranscript()

            def find_transcript(self, _language_codes):
                return BrokenTranscript()

            def find_generated_transcript(self, _language_codes):
                return WorkingTranscript()

        class FakeApi:
            def list(self, _video_id):
                return FakeTranscriptList()

        monkeypatch.setattr("src.core.transcript.get_video_id", lambda _url: "abc123")
        monkeypatch.setattr("src.core.transcript.YouTubeTranscriptApi", FakeApi)

        result = fetch_transcript("https://www.youtube.com/watch?v=abc123def45")
        assert result == [("hola mundo", 0.0, 2.0)]
