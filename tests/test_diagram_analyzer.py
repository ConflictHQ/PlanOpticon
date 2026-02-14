"""Tests for the rewritten diagram analyzer."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from video_processor.analyzers.diagram_analyzer import (
    DiagramAnalyzer,
    _parse_json_response,
)
from video_processor.models import DiagramResult, DiagramType, ScreenCapture


class TestParseJsonResponse:
    def test_plain_json(self):
        result = _parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_markdown_fenced(self):
        text = '```json\n{"key": "value"}\n```'
        result = _parse_json_response(text)
        assert result == {"key": "value"}

    def test_json_in_text(self):
        text = 'Here is the result: {"is_diagram": true, "confidence": 0.8} as requested.'
        result = _parse_json_response(text)
        assert result["is_diagram"] is True

    def test_empty_string(self):
        assert _parse_json_response("") is None

    def test_invalid_json(self):
        assert _parse_json_response("not json at all") is None


class TestDiagramAnalyzer:
    @pytest.fixture
    def mock_pm(self):
        return MagicMock()

    @pytest.fixture
    def analyzer(self, mock_pm):
        return DiagramAnalyzer(provider_manager=mock_pm)

    @pytest.fixture
    def fake_frame(self, tmp_path):
        """Create a tiny JPEG-like file for testing."""
        fp = tmp_path / "frame_0.jpg"
        fp.write_bytes(b"\xff\xd8\xff fake image data")
        return fp

    def test_classify_frame_diagram(self, analyzer, mock_pm, fake_frame):
        mock_pm.analyze_image.return_value = json.dumps({
            "is_diagram": True,
            "diagram_type": "flowchart",
            "confidence": 0.85,
            "brief_description": "A flowchart showing login process"
        })
        result = analyzer.classify_frame(fake_frame)
        assert result["is_diagram"] is True
        assert result["confidence"] == 0.85

    def test_classify_frame_not_diagram(self, analyzer, mock_pm, fake_frame):
        mock_pm.analyze_image.return_value = json.dumps({
            "is_diagram": False,
            "diagram_type": "unknown",
            "confidence": 0.1,
            "brief_description": "A person speaking"
        })
        result = analyzer.classify_frame(fake_frame)
        assert result["is_diagram"] is False

    def test_classify_frame_failure(self, analyzer, mock_pm, fake_frame):
        mock_pm.analyze_image.return_value = "I cannot parse this image"
        result = analyzer.classify_frame(fake_frame)
        assert result["is_diagram"] is False
        assert result["confidence"] == 0.0

    def test_analyze_single_pass(self, analyzer, mock_pm, fake_frame):
        mock_pm.analyze_image.return_value = json.dumps({
            "diagram_type": "architecture",
            "description": "Microservices architecture",
            "text_content": "Service A, Service B",
            "elements": ["Service A", "Service B"],
            "relationships": ["A -> B: calls"],
            "mermaid": "graph LR\n    A-->B",
            "chart_data": None
        })
        result = analyzer.analyze_diagram_single_pass(fake_frame)
        assert result["diagram_type"] == "architecture"
        assert result["mermaid"] == "graph LR\n    A-->B"

    def test_process_frames_high_confidence_diagram(self, analyzer, mock_pm, tmp_path):
        # Create fake frames
        frames = []
        for i in range(3):
            fp = tmp_path / f"frame_{i}.jpg"
            fp.write_bytes(b"\xff\xd8\xff fake")
            frames.append(fp)

        diagrams_dir = tmp_path / "diagrams"
        captures_dir = tmp_path / "captures"

        # Frame 0: high confidence diagram
        # Frame 1: low confidence (skip)
        # Frame 2: medium confidence (screengrab)
        classify_responses = [
            json.dumps({"is_diagram": True, "diagram_type": "flowchart", "confidence": 0.9, "brief_description": "flow"}),
            json.dumps({"is_diagram": False, "diagram_type": "unknown", "confidence": 0.1, "brief_description": "nothing"}),
            json.dumps({"is_diagram": True, "diagram_type": "slide", "confidence": 0.5, "brief_description": "a slide"}),
        ]
        analysis_response = json.dumps({
            "diagram_type": "flowchart",
            "description": "Login flow",
            "text_content": "Start -> End",
            "elements": ["Start", "End"],
            "relationships": ["Start -> End"],
            "mermaid": "graph LR\n    Start-->End",
            "chart_data": None
        })

        # Calls are interleaved per-frame:
        # call 0: classify frame 0 (high conf)
        # call 1: analyze frame 0 (full analysis)
        # call 2: classify frame 1 (low conf - skip)
        # call 3: classify frame 2 (medium conf)
        # call 4: caption frame 2 (screengrab)
        call_sequence = [
            classify_responses[0],   # classify frame 0
            analysis_response,       # analyze frame 0
            classify_responses[1],   # classify frame 1
            classify_responses[2],   # classify frame 2
            "A slide about something",  # caption frame 2
        ]
        call_count = [0]
        def side_effect(image_bytes, prompt, max_tokens=4096):
            idx = call_count[0]
            call_count[0] += 1
            return call_sequence[idx]

        mock_pm.analyze_image.side_effect = side_effect

        diagrams, captures = analyzer.process_frames(frames, diagrams_dir, captures_dir)

        assert len(diagrams) == 1
        assert diagrams[0].frame_index == 0
        assert diagrams[0].diagram_type == DiagramType.flowchart
        assert diagrams[0].mermaid == "graph LR\n    Start-->End"

        assert len(captures) == 1
        assert captures[0].frame_index == 2

        # Check files were saved
        assert (diagrams_dir / "diagram_0.jpg").exists()
        assert (diagrams_dir / "diagram_0.mermaid").exists()
        assert (diagrams_dir / "diagram_0.json").exists()
        assert (captures_dir / "capture_0.jpg").exists()
        assert (captures_dir / "capture_0.json").exists()

    def test_process_frames_analysis_failure_falls_back(self, analyzer, mock_pm, tmp_path):
        fp = tmp_path / "frame_0.jpg"
        fp.write_bytes(b"\xff\xd8\xff fake")
        captures_dir = tmp_path / "captures"

        # High confidence classification but analysis fails
        call_count = [0]
        def side_effect(image_bytes, prompt, max_tokens=4096):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                return json.dumps({"is_diagram": True, "diagram_type": "chart", "confidence": 0.8, "brief_description": "chart"})
            if idx == 1:
                return "This is not valid JSON"  # Analysis fails
            return "A chart showing data"  # Caption

        mock_pm.analyze_image.side_effect = side_effect

        diagrams, captures = analyzer.process_frames([fp], captures_dir=captures_dir)
        assert len(diagrams) == 0
        assert len(captures) == 1
        assert captures[0].frame_index == 0
