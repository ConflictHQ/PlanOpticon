"""Tests for the rewritten diagram analyzer."""

import json
from unittest.mock import MagicMock

import pytest

from video_processor.analyzers.diagram_analyzer import (
    DiagramAnalyzer,
    _parse_json_response,
)
from video_processor.models import DiagramType


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
        return DiagramAnalyzer(provider_manager=mock_pm, max_workers=1)

    @pytest.fixture
    def fake_frame(self, tmp_path):
        """Create a tiny JPEG-like file for testing."""
        fp = tmp_path / "frame_0.jpg"
        fp.write_bytes(b"\xff\xd8\xff fake image data")
        return fp

    def test_classify_frame_diagram(self, analyzer, mock_pm, fake_frame):
        mock_pm.analyze_image.return_value = json.dumps(
            {
                "is_diagram": True,
                "diagram_type": "flowchart",
                "confidence": 0.85,
                "brief_description": "A flowchart showing login process",
            }
        )
        result = analyzer.classify_frame(fake_frame)
        assert result["is_diagram"] is True
        assert result["confidence"] == 0.85

    def test_classify_frame_not_diagram(self, analyzer, mock_pm, fake_frame):
        mock_pm.analyze_image.return_value = json.dumps(
            {
                "is_diagram": False,
                "diagram_type": "unknown",
                "confidence": 0.1,
                "brief_description": "A person speaking",
            }
        )
        result = analyzer.classify_frame(fake_frame)
        assert result["is_diagram"] is False

    def test_classify_frame_failure(self, analyzer, mock_pm, fake_frame):
        mock_pm.analyze_image.return_value = "I cannot parse this image"
        result = analyzer.classify_frame(fake_frame)
        assert result["is_diagram"] is False
        assert result["confidence"] == 0.0

    def test_analyze_single_pass(self, analyzer, mock_pm, fake_frame):
        mock_pm.analyze_image.return_value = json.dumps(
            {
                "diagram_type": "architecture",
                "description": "Microservices architecture",
                "text_content": "Service A, Service B",
                "elements": ["Service A", "Service B"],
                "relationships": ["A -> B: calls"],
                "mermaid": "graph LR\n    A-->B",
                "chart_data": None,
            }
        )
        result = analyzer.analyze_diagram_single_pass(fake_frame)
        assert result["diagram_type"] == "architecture"
        assert result["mermaid"] == "graph LR\n    A-->B"

    def test_process_frames_high_confidence_diagram(self, analyzer, mock_pm, tmp_path):
        # Create fake frames with distinct content so hashes differ
        frames = []
        for i in range(3):
            fp = tmp_path / f"frame_{i}.jpg"
            fp.write_bytes(b"\xff\xd8\xff fake" + bytes([i]) * 100)
            frames.append(fp)

        diagrams_dir = tmp_path / "diagrams"
        captures_dir = tmp_path / "captures"

        # Frame 0: high confidence diagram
        # Frame 1: low confidence (skip)
        # Frame 2: medium confidence (screengrab)

        # Use prompt-based routing since parallel execution doesn't guarantee call order
        frame_classify = {
            0: {
                "is_diagram": True,
                "diagram_type": "flowchart",
                "confidence": 0.9,
                "brief_description": "flow",
            },
            1: {
                "is_diagram": False,
                "diagram_type": "unknown",
                "confidence": 0.1,
                "brief_description": "nothing",
            },
            2: {
                "is_diagram": True,
                "diagram_type": "slide",
                "confidence": 0.5,
                "brief_description": "a slide",
            },
        }
        analysis_response = {
            "diagram_type": "flowchart",
            "description": "Login flow",
            "text_content": "Start -> End",
            "elements": ["Start", "End"],
            "relationships": ["Start -> End"],
            "mermaid": "graph LR\n    Start-->End",
            "chart_data": None,
        }
        screenshot_response = {
            "content_type": "slide",
            "caption": "A slide about something",
            "text_content": "Key Points\n- Item 1\n- Item 2",
            "entities": ["Item 1", "Item 2"],
            "topics": ["presentation"],
        }

        def side_effect(image_bytes, prompt, max_tokens=4096):
            # Identify frame by content
            for i in range(3):
                marker = b"\xff\xd8\xff fake" + bytes([i]) * 100
                if image_bytes == marker:
                    frame_idx = i
                    break
            else:
                return json.dumps({"is_diagram": False, "confidence": 0.0})

            if "Examine this image" in prompt:
                return json.dumps(frame_classify[frame_idx])
            elif "Analyze this diagram" in prompt:
                return json.dumps(analysis_response)
            elif "Extract all visible knowledge" in prompt:
                return json.dumps(screenshot_response)
            return json.dumps({"is_diagram": False, "confidence": 0.0})

        mock_pm.analyze_image.side_effect = side_effect

        diagrams, captures = analyzer.process_frames(frames, diagrams_dir, captures_dir)

        assert len(diagrams) == 1
        assert diagrams[0].frame_index == 0
        assert diagrams[0].diagram_type == DiagramType.flowchart
        assert diagrams[0].mermaid == "graph LR\n    Start-->End"

        assert len(captures) == 1
        assert captures[0].frame_index == 2
        assert captures[0].content_type == "slide"
        assert captures[0].text_content == "Key Points\n- Item 1\n- Item 2"
        assert "Item 1" in captures[0].entities
        assert "presentation" in captures[0].topics

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
        def side_effect(image_bytes, prompt, max_tokens=4096):
            if "Examine this image" in prompt:
                return json.dumps(
                    {
                        "is_diagram": True,
                        "diagram_type": "chart",
                        "confidence": 0.8,
                        "brief_description": "chart",
                    }
                )
            if "Analyze this diagram" in prompt:
                return "This is not valid JSON"  # Analysis fails
            if "Extract all visible knowledge" in prompt:
                return json.dumps(
                    {
                        "content_type": "chart",
                        "caption": "A chart showing data",
                        "text_content": "Sales Q1 Q2 Q3",
                        "entities": ["Sales"],
                        "topics": ["metrics"],
                    }
                )
            return "{}"

        mock_pm.analyze_image.side_effect = side_effect

        diagrams, captures = analyzer.process_frames([fp], captures_dir=captures_dir)
        assert len(diagrams) == 0
        assert len(captures) == 1
        assert captures[0].frame_index == 0

    def test_extract_screenshot_knowledge(self, analyzer, mock_pm, fake_frame):
        mock_pm.analyze_image.return_value = json.dumps(
            {
                "content_type": "code",
                "caption": "Python source code",
                "text_content": "def main():\n    print('hello')",
                "entities": ["Python", "main function"],
                "topics": ["programming", "source code"],
            }
        )
        result = analyzer.extract_screenshot_knowledge(fake_frame)
        assert result["content_type"] == "code"
        assert "Python" in result["entities"]
        assert "def main" in result["text_content"]

    def test_extract_screenshot_knowledge_failure(self, analyzer, mock_pm, fake_frame):
        mock_pm.analyze_image.return_value = "not json"
        result = analyzer.extract_screenshot_knowledge(fake_frame)
        assert result == {}

    def test_process_frames_uses_cache(self, mock_pm, tmp_path):
        """Verify that cached results skip API calls on re-run."""
        fp = tmp_path / "frame_0.jpg"
        fp.write_bytes(b"\xff\xd8\xff cached test data")
        captures_dir = tmp_path / "captures"
        cache_dir = tmp_path / "cache"

        def side_effect(image_bytes, prompt, max_tokens=4096):
            if "Examine this image" in prompt:
                return json.dumps(
                    {
                        "is_diagram": True,
                        "diagram_type": "slide",
                        "confidence": 0.5,
                        "brief_description": "a slide",
                    }
                )
            if "Extract all visible knowledge" in prompt:
                return json.dumps(
                    {
                        "content_type": "slide",
                        "caption": "Cached slide",
                        "text_content": "cached text",
                        "entities": ["CachedEntity"],
                        "topics": ["caching"],
                    }
                )
            return "{}"

        mock_pm.analyze_image.side_effect = side_effect

        analyzer = DiagramAnalyzer(provider_manager=mock_pm, max_workers=1)

        # First run — should call the API
        diagrams, captures = analyzer.process_frames(
            [fp], captures_dir=captures_dir, cache_dir=cache_dir
        )
        assert len(captures) == 1
        assert mock_pm.analyze_image.call_count > 0

        # Reset mock but keep cache
        mock_pm.analyze_image.reset_mock()
        mock_pm.analyze_image.side_effect = side_effect

        # Clean output dirs so we can re-run
        import shutil

        if captures_dir.exists():
            shutil.rmtree(captures_dir)

        # Second run — should use cache, fewer API calls
        diagrams2, captures2 = analyzer.process_frames(
            [fp], captures_dir=captures_dir, cache_dir=cache_dir
        )
        assert len(captures2) == 1
        assert mock_pm.analyze_image.call_count == 0  # All from cache
        assert captures2[0].caption == "Cached slide"

    def test_process_frames_parallel_workers(self, mock_pm, tmp_path):
        """Verify parallel processing with multiple workers produces correct results."""
        frames = []
        for i in range(5):
            fp = tmp_path / f"frame_{i}.jpg"
            fp.write_bytes(b"\xff\xd8\xff data" + bytes([i]) * 200)
            frames.append(fp)

        # All medium confidence — all should become screengrabs
        def side_effect(image_bytes, prompt, max_tokens=4096):
            if "Examine this image" in prompt:
                return json.dumps(
                    {
                        "is_diagram": True,
                        "diagram_type": "slide",
                        "confidence": 0.5,
                        "brief_description": "slide",
                    }
                )
            if "Extract all visible knowledge" in prompt:
                return json.dumps(
                    {
                        "content_type": "slide",
                        "caption": "A slide",
                        "text_content": "text",
                        "entities": [],
                        "topics": [],
                    }
                )
            return "{}"

        mock_pm.analyze_image.side_effect = side_effect

        analyzer = DiagramAnalyzer(provider_manager=mock_pm, max_workers=3)
        diagrams, captures = analyzer.process_frames(frames)

        assert len(diagrams) == 0
        assert len(captures) == 5
        # Verify all frame indices are present
        indices = {c.frame_index for c in captures}
        assert indices == {0, 1, 2, 3, 4}
