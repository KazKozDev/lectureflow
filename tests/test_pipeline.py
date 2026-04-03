"""Tests for analysis pipeline caching and detailed-mode behavior."""

import importlib
import sys
import types


class FakeSegmenter:
    """Lightweight segmenter stub for pipeline tests."""

    def __init__(self) -> None:
        self.model = object()

    def segment(self, _segments):
        return [
            {
                "start_time": 0.0,
                "end_time": 10.0,
                "text": "first section",
                "segment_count": 1,
            },
            {
                "start_time": 10.0,
                "end_time": 20.0,
                "text": "second section",
                "segment_count": 1,
            },
        ]


class FakeAnnotator:
    """Lightweight annotator stub for pipeline tests."""

    def __init__(self, model=None) -> None:
        self.model = model

    def annotate_segments(self, segments):
        for i, segment in enumerate(segments, start=1):
            segment["topic"] = f"topic {i}"
        return segments


def load_pipeline_module(monkeypatch):
    """Import pipeline with lightweight fake ML modules injected."""
    fake_segmenter_module = types.ModuleType("src.core.segmenter")
    fake_segmenter_module.SemanticSegmenter = FakeSegmenter

    fake_annotator_module = types.ModuleType("src.core.annotator")
    fake_annotator_module.TopicAnnotator = FakeAnnotator

    monkeypatch.setitem(sys.modules, "src.core.segmenter", fake_segmenter_module)
    monkeypatch.setitem(sys.modules, "src.core.annotator", fake_annotator_module)
    sys.modules.pop("src.core.pipeline", None)
    return importlib.import_module("src.core.pipeline")


def test_detailed_mode_uses_single_global_llm_pass(monkeypatch, mock_llm):
    """Detailed mode should use one global generation instead of per-segment LLM calls."""

    pipeline_module = load_pipeline_module(monkeypatch)

    monkeypatch.setattr(
        pipeline_module,
        "fetch_transcript",
        lambda _url: [("raw", 0.0, 20.0)],
    )

    called = {"global": 0, "segment": 0}

    def fake_global(segments, llm_client, mode, config_path=None, language=None):
        called["global"] += 1
        assert mode == "detailed"
        assert len(segments) == 2
        return "# Detailed output"

    def fake_segment(*args, **kwargs):
        called["segment"] += 1
        raise AssertionError("Detailed mode should not call per-segment post-processing")

    monkeypatch.setattr("src.core.postprocessor.generate_global_markdown", fake_global)
    monkeypatch.setattr(pipeline_module, "post_process_segments", fake_segment)

    pipeline = pipeline_module.AnalysisPipeline(llm_client=mock_llm, db_path=None)
    result = pipeline.analyze("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result["markdown"] == "# Detailed output"
    assert called == {"global": 1, "segment": 0}


def test_exact_result_cache_reuses_completed_analysis(monkeypatch, mock_llm):
    """Same mode/model/language should reuse the exact finished result cache."""

    pipeline_module = load_pipeline_module(monkeypatch)

    transcript_calls = {"count": 0}
    global_calls = {"count": 0}

    def fake_fetch(_url):
        transcript_calls["count"] += 1
        return [("raw", 0.0, 20.0)]

    def fake_global(_segments, _llm_client, _mode, config_path=None, language=None):
        global_calls["count"] += 1
        return f"# Detailed output in {language}"

    monkeypatch.setattr(pipeline_module, "fetch_transcript", fake_fetch)
    monkeypatch.setattr("src.core.postprocessor.generate_global_markdown", fake_global)

    pipeline = pipeline_module.AnalysisPipeline(llm_client=mock_llm, db_path=None)

    first = pipeline.analyze(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        mode="detailed",
        model_name="model-a",
        language="English",
    )
    second = pipeline.analyze(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        mode="detailed",
        model_name="model-a",
        language="English",
    )

    assert first["markdown"] == second["markdown"]
    assert transcript_calls["count"] == 1
    assert global_calls["count"] == 1


def test_persisted_exact_cache_reuses_saved_result(monkeypatch, mock_llm, temp_db):
    """A new pipeline instance should reuse an exact cached result from SQLite."""

    pipeline_module = load_pipeline_module(monkeypatch)

    transcript_calls = {"count": 0}
    global_calls = {"count": 0}

    def fake_fetch(_url):
        transcript_calls["count"] += 1
        return [("raw", 0.0, 20.0)]

    def fake_global(_segments, _llm_client, _mode, config_path=None, language=None):
        global_calls["count"] += 1
        return "# Persisted detailed output"

    monkeypatch.setattr(pipeline_module, "fetch_transcript", fake_fetch)
    monkeypatch.setattr("src.core.postprocessor.generate_global_markdown", fake_global)

    first_pipeline = pipeline_module.AnalysisPipeline(llm_client=mock_llm, db_path=temp_db)
    first_pipeline.analyze(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        mode="detailed",
        model_name="model-a",
        language="English",
    )
    first_pipeline.db.close()

    second_pipeline = pipeline_module.AnalysisPipeline(llm_client=mock_llm, db_path=temp_db)
    cached = second_pipeline.analyze(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        mode="detailed",
        model_name="model-a",
        language="English",
    )

    assert cached["markdown"] == "# Persisted detailed output"
    assert transcript_calls["count"] == 1
    assert global_calls["count"] == 1
