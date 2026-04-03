"""Tests for export formatters."""

import json

import pytest

from src.export.formatters import to_json, to_markdown, to_srt, to_youtube_description


@pytest.fixture
def export_segments():
    return [
        {
            "start_time": 0.0,
            "end_time": 60.0,
            "text": "Introduction to the topic",
            "topic": "Introduction",
            "improved_topic": "Getting Started",
            "improved_text": "Welcome to this introduction.",
        },
        {
            "start_time": 60.0,
            "end_time": 180.0,
            "text": "Main content here",
            "topic": "Main",
            "improved_topic": "Core Concepts",
            "improved_text": "The core concepts are discussed.",
        },
    ]


class TestMarkdownExport:
    def test_basic_format(self, export_segments):
        md = to_markdown(export_segments)
        assert "**[00:00 - 01:00] Getting Started**" in md
        assert "**[01:00 - 03:00] Core Concepts**" in md
        assert "---" in md

    def test_empty_segments(self):
        assert to_markdown([]) == ""


class TestJsonExport:
    def test_valid_json(self, export_segments):
        result = to_json(export_segments, "test_vid")
        parsed = json.loads(result)
        assert parsed["video_id"] == "test_vid"
        assert len(parsed["segments"]) == 2
        assert parsed["segments"][0]["start_formatted"] == "00:00"

    def test_empty_segments(self):
        result = json.loads(to_json([], "vid"))
        assert result["segments"] == []


class TestYoutubeDescription:
    def test_format(self, export_segments):
        desc = to_youtube_description(export_segments)
        assert "00:00 — Getting Started" in desc
        assert "01:00 — Core Concepts" in desc
        assert desc.startswith("Timestamps:")


class TestSrtExport:
    def test_format(self, export_segments):
        srt = to_srt(export_segments)
        assert "1\n" in srt
        assert "00:00:00,000 --> 00:01:00,000" in srt
        assert "2\n" in srt
