"""Tests for the agentic processing orchestrator."""

import json
from unittest.mock import MagicMock, patch

import pytest

from video_processor.agent.orchestrator import AgentOrchestrator


class TestPlanCreation:
    def test_basic_plan(self):
        agent = AgentOrchestrator()
        plan = agent._create_plan("test.mp4", "basic")
        steps = [s["step"] for s in plan]
        assert "extract_frames" in steps
        assert "extract_audio" in steps
        assert "transcribe" in steps
        assert "extract_key_points" in steps
        assert "extract_action_items" in steps
        assert "generate_reports" in steps
        assert "detect_diagrams" not in steps

    def test_standard_plan(self):
        agent = AgentOrchestrator()
        plan = agent._create_plan("test.mp4", "standard")
        steps = [s["step"] for s in plan]
        assert "detect_diagrams" in steps
        assert "build_knowledge_graph" in steps
        assert "deep_analysis" not in steps

    def test_comprehensive_plan(self):
        agent = AgentOrchestrator()
        plan = agent._create_plan("test.mp4", "comprehensive")
        steps = [s["step"] for s in plan]
        assert "detect_diagrams" in steps
        assert "deep_analysis" in steps
        assert "cross_reference" in steps


class TestAdaptPlan:
    def test_adapts_for_long_transcript(self):
        agent = AgentOrchestrator()
        agent._plan = [{"step": "generate_reports", "priority": "required"}]
        long_text = "word " * 3000  # > 10000 chars
        agent._adapt_plan("transcribe", {"text": long_text})
        steps = [s["step"] for s in agent._plan]
        assert "deep_analysis" in steps

    def test_no_adapt_for_short_transcript(self):
        agent = AgentOrchestrator()
        agent._plan = [{"step": "generate_reports", "priority": "required"}]
        agent._adapt_plan("transcribe", {"text": "Short text"})
        steps = [s["step"] for s in agent._plan]
        assert "deep_analysis" not in steps

    def test_adapts_for_many_diagrams(self):
        agent = AgentOrchestrator()
        agent._plan = [{"step": "generate_reports", "priority": "required"}]
        diagrams = [MagicMock() for _ in range(5)]
        agent._adapt_plan("detect_diagrams", {"diagrams": diagrams, "captures": []})
        steps = [s["step"] for s in agent._plan]
        assert "cross_reference" in steps

    def test_insight_for_many_captures(self):
        agent = AgentOrchestrator()
        agent._plan = []
        captures = [MagicMock() for _ in range(5)]
        diagrams = [MagicMock() for _ in range(2)]
        agent._adapt_plan("detect_diagrams", {"diagrams": diagrams, "captures": captures})
        assert len(agent._insights) == 1
        assert "uncertain frames" in agent._insights[0]

    def test_no_duplicate_steps(self):
        agent = AgentOrchestrator()
        agent._plan = [{"step": "deep_analysis", "priority": "comprehensive"}]
        long_text = "word " * 3000
        agent._adapt_plan("transcribe", {"text": long_text})
        deep_steps = [s for s in agent._plan if s["step"] == "deep_analysis"]
        assert len(deep_steps) == 1


class TestFallbacks:
    def test_diagram_fallback(self):
        agent = AgentOrchestrator()
        assert agent._get_fallback("detect_diagrams") == "screengrab_fallback"

    def test_no_fallback_for_unknown(self):
        agent = AgentOrchestrator()
        assert agent._get_fallback("transcribe") is None


class TestInsights:
    def test_insights_property(self):
        agent = AgentOrchestrator()
        agent._insights = ["Insight 1", "Insight 2"]
        assert agent.insights == ["Insight 1", "Insight 2"]
        # Should return a copy
        agent.insights.append("should not modify internal")
        assert len(agent._insights) == 2

    def test_deep_analysis_populates_insights(self):
        pm = MagicMock()
        pm.chat.return_value = json.dumps({
            "decisions": ["Decided to use microservices"],
            "risks": ["Timeline is tight"],
            "follow_ups": [],
            "tensions": [],
        })
        agent = AgentOrchestrator(provider_manager=pm)
        agent._results["transcribe"] = {"text": "Some long transcript text here"}
        result = agent._deep_analysis("/tmp")
        assert "decisions" in result
        assert any("microservices" in i for i in agent._insights)
        assert any("Timeline" in i for i in agent._insights)

    def test_deep_analysis_handles_error(self):
        pm = MagicMock()
        pm.chat.side_effect = Exception("API error")
        agent = AgentOrchestrator(provider_manager=pm)
        agent._results["transcribe"] = {"text": "some text"}
        result = agent._deep_analysis("/tmp")
        assert result == {}

    def test_deep_analysis_no_transcript(self):
        agent = AgentOrchestrator()
        agent._results["transcribe"] = {"text": ""}
        result = agent._deep_analysis("/tmp")
        assert result == {}


class TestBuildManifest:
    def test_builds_from_results(self):
        agent = AgentOrchestrator()
        agent._results = {
            "extract_frames": {"frames": [1, 2, 3], "paths": ["/a.jpg", "/b.jpg"]},
            "extract_audio": {"audio_path": "/audio.wav", "properties": {"duration": 60.0}},
            "detect_diagrams": {"diagrams": [], "captures": []},
            "extract_key_points": {"key_points": []},
            "extract_action_items": {"action_items": []},
        }
        from pathlib import Path

        manifest = agent._build_manifest(Path("test.mp4"), Path("/out"), "Test", 5.0)
        assert manifest.video.title == "Test"
        assert manifest.stats.frames_extracted == 3
        assert manifest.stats.duration_seconds == 5.0
        assert manifest.video.duration_seconds == 60.0

    def test_handles_missing_results(self):
        agent = AgentOrchestrator()
        agent._results = {}
        from pathlib import Path

        manifest = agent._build_manifest(Path("test.mp4"), Path("/out"), None, 1.0)
        assert manifest.video.title == "Analysis of test"
        assert manifest.stats.frames_extracted == 0

    def test_handles_error_results(self):
        agent = AgentOrchestrator()
        agent._results = {
            "extract_frames": {"error": "failed"},
            "detect_diagrams": {"error": "also failed"},
        }
        from pathlib import Path

        manifest = agent._build_manifest(Path("vid.mp4"), Path("/out"), None, 2.0)
        assert manifest.stats.frames_extracted == 0
        assert len(manifest.diagrams) == 0
