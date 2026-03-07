"""Tests for the planning agent, skill registry, KB context, and agent loop."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from video_processor.agent.skills.base import (
    AgentContext,
    Artifact,
    Skill,
    _skills,
    get_skill,
    list_skills,
    register_skill,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_skill_registry():
    """Save and restore the global skill registry between tests."""
    original = dict(_skills)
    yield
    _skills.clear()
    _skills.update(original)


class _DummySkill(Skill):
    name = "dummy_test_skill"
    description = "A dummy skill for testing"

    def execute(self, context: AgentContext, **kwargs) -> Artifact:
        return Artifact(
            name="dummy artifact",
            content="dummy content",
            artifact_type="document",
        )


class _NoLLMSkill(Skill):
    """Skill that doesn't require provider_manager."""

    name = "nollm_skill"
    description = "Works without LLM"

    def execute(self, context: AgentContext, **kwargs) -> Artifact:
        return Artifact(
            name="nollm artifact",
            content="generated",
            artifact_type="document",
        )

    def can_execute(self, context: AgentContext) -> bool:
        return context.knowledge_graph is not None


# ---------------------------------------------------------------------------
# Skill registry
# ---------------------------------------------------------------------------


class TestSkillRegistry:
    def test_register_and_get(self):
        skill = _DummySkill()
        register_skill(skill)
        assert get_skill("dummy_test_skill") is skill

    def test_get_unknown_returns_none(self):
        assert get_skill("no_such_skill_xyz") is None

    def test_list_skills(self):
        s1 = _DummySkill()
        register_skill(s1)
        skills = list_skills()
        assert any(s.name == "dummy_test_skill" for s in skills)

    def test_list_skills_empty(self):
        _skills.clear()
        assert list_skills() == []


# ---------------------------------------------------------------------------
# AgentContext dataclass
# ---------------------------------------------------------------------------


class TestAgentContext:
    def test_defaults(self):
        ctx = AgentContext()
        assert ctx.knowledge_graph is None
        assert ctx.query_engine is None
        assert ctx.provider_manager is None
        assert ctx.planning_entities == []
        assert ctx.user_requirements == {}
        assert ctx.conversation_history == []
        assert ctx.artifacts == []
        assert ctx.config == {}

    def test_with_values(self):
        mock_kg = MagicMock()
        mock_qe = MagicMock()
        mock_pm = MagicMock()
        ctx = AgentContext(
            knowledge_graph=mock_kg,
            query_engine=mock_qe,
            provider_manager=mock_pm,
            config={"key": "value"},
        )
        assert ctx.knowledge_graph is mock_kg
        assert ctx.config == {"key": "value"}

    def test_conversation_history_is_mutable(self):
        ctx = AgentContext()
        ctx.conversation_history.append({"role": "user", "content": "hello"})
        assert len(ctx.conversation_history) == 1


# ---------------------------------------------------------------------------
# Artifact dataclass
# ---------------------------------------------------------------------------


class TestArtifact:
    def test_basic(self):
        a = Artifact(name="Plan", content="# Plan\n...", artifact_type="project_plan")
        assert a.name == "Plan"
        assert a.format == "markdown"  # default
        assert a.metadata == {}

    def test_with_metadata(self):
        a = Artifact(
            name="Tasks",
            content="[]",
            artifact_type="task_list",
            format="json",
            metadata={"source": "kg"},
        )
        assert a.format == "json"
        assert a.metadata["source"] == "kg"


# ---------------------------------------------------------------------------
# Skill.can_execute
# ---------------------------------------------------------------------------


class TestSkillCanExecute:
    def test_default_requires_kg_and_pm(self):
        skill = _DummySkill()
        ctx_no_kg = AgentContext(provider_manager=MagicMock())
        assert not skill.can_execute(ctx_no_kg)

        ctx_no_pm = AgentContext(knowledge_graph=MagicMock())
        assert not skill.can_execute(ctx_no_pm)

        ctx_both = AgentContext(knowledge_graph=MagicMock(), provider_manager=MagicMock())
        assert skill.can_execute(ctx_both)


# ---------------------------------------------------------------------------
# KBContext
# ---------------------------------------------------------------------------


class TestKBContext:
    def test_add_source_nonexistent_raises(self, tmp_path):
        from video_processor.agent.kb_context import KBContext

        ctx = KBContext()
        with pytest.raises(FileNotFoundError, match="Not found"):
            ctx.add_source(tmp_path / "nonexistent.json")

    def test_add_source_file(self, tmp_path):
        from video_processor.agent.kb_context import KBContext

        f = tmp_path / "kg.json"
        f.write_text("{}")
        ctx = KBContext()
        ctx.add_source(f)
        assert len(ctx.sources) == 1
        assert ctx.sources[0] == f.resolve()

    def test_add_source_directory(self, tmp_path):
        from video_processor.agent.kb_context import KBContext

        with patch(
            "video_processor.integrators.graph_discovery.find_knowledge_graphs",
            return_value=[tmp_path / "a.db"],
        ):
            ctx = KBContext()
            ctx.add_source(tmp_path)
            assert len(ctx.sources) == 1

    def test_knowledge_graph_before_load_raises(self):
        from video_processor.agent.kb_context import KBContext

        ctx = KBContext()
        with pytest.raises(RuntimeError, match="Call load"):
            _ = ctx.knowledge_graph

    def test_query_engine_before_load_raises(self):
        from video_processor.agent.kb_context import KBContext

        ctx = KBContext()
        with pytest.raises(RuntimeError, match="Call load"):
            _ = ctx.query_engine

    def test_summary_no_data(self):
        from video_processor.agent.kb_context import KBContext

        ctx = KBContext()
        assert ctx.summary() == "No knowledge base loaded."

    def test_load_json_and_summary(self, tmp_path):
        from video_processor.agent.kb_context import KBContext

        kg_data = {"nodes": [], "relationships": []}
        f = tmp_path / "kg.json"
        f.write_text(json.dumps(kg_data))

        ctx = KBContext()
        ctx.add_source(f)
        ctx.load()

        summary = ctx.summary()
        assert "Knowledge base" in summary
        assert "Entities" in summary
        assert "Relationships" in summary


# ---------------------------------------------------------------------------
# PlanningAgent
# ---------------------------------------------------------------------------


class TestPlanningAgent:
    def test_from_kb_paths(self, tmp_path):
        from video_processor.agent.agent_loop import PlanningAgent

        kg_data = {"nodes": [], "relationships": []}
        f = tmp_path / "kg.json"
        f.write_text(json.dumps(kg_data))

        agent = PlanningAgent.from_kb_paths([f], provider_manager=None)
        assert agent.context.knowledge_graph is not None
        assert agent.context.provider_manager is None

    def test_execute_with_mock_provider(self, tmp_path):
        from video_processor.agent.agent_loop import PlanningAgent

        # Register a dummy skill
        skill = _DummySkill()
        register_skill(skill)

        mock_pm = MagicMock()
        mock_pm.chat.return_value = json.dumps([{"skill": "dummy_test_skill", "params": {}}])

        ctx = AgentContext(
            knowledge_graph=MagicMock(),
            query_engine=MagicMock(),
            provider_manager=mock_pm,
        )
        # Mock stats().to_text()
        ctx.query_engine.stats.return_value.to_text.return_value = "3 entities"

        agent = PlanningAgent(context=ctx)
        artifacts = agent.execute("generate a plan")

        assert len(artifacts) == 1
        assert artifacts[0].name == "dummy artifact"
        mock_pm.chat.assert_called_once()

    def test_execute_no_provider_keyword_match(self):
        from video_processor.agent.agent_loop import PlanningAgent

        skill = _DummySkill()
        register_skill(skill)

        ctx = AgentContext(
            knowledge_graph=MagicMock(),
            provider_manager=None,
        )

        agent = PlanningAgent(context=ctx)
        # "dummy" is a keyword in the skill name, but can_execute needs provider_manager
        # so it should return empty
        artifacts = agent.execute("dummy request")
        assert artifacts == []

    def test_execute_keyword_match_nollm_skill(self):
        from video_processor.agent.agent_loop import PlanningAgent

        skill = _NoLLMSkill()
        register_skill(skill)

        ctx = AgentContext(
            knowledge_graph=MagicMock(),
            provider_manager=None,
        )

        agent = PlanningAgent(context=ctx)
        # "nollm" is in the skill name
        artifacts = agent.execute("nollm stuff")
        assert len(artifacts) == 1
        assert artifacts[0].name == "nollm artifact"

    def test_execute_skips_unknown_skills(self):
        from video_processor.agent.agent_loop import PlanningAgent

        mock_pm = MagicMock()
        mock_pm.chat.return_value = json.dumps([{"skill": "nonexistent_skill_xyz", "params": {}}])

        ctx = AgentContext(
            knowledge_graph=MagicMock(),
            query_engine=MagicMock(),
            provider_manager=mock_pm,
        )
        ctx.query_engine.stats.return_value.to_text.return_value = ""

        agent = PlanningAgent(context=ctx)
        artifacts = agent.execute("do something")
        assert artifacts == []

    def test_chat_no_provider(self):
        from video_processor.agent.agent_loop import PlanningAgent

        ctx = AgentContext(provider_manager=None)
        agent = PlanningAgent(context=ctx)

        reply = agent.chat("hello")
        assert "requires" in reply.lower() or "provider" in reply.lower()

    def test_chat_with_provider(self):
        from video_processor.agent.agent_loop import PlanningAgent

        mock_pm = MagicMock()
        mock_pm.chat.return_value = "I can help you plan."

        ctx = AgentContext(
            knowledge_graph=MagicMock(),
            query_engine=MagicMock(),
            provider_manager=mock_pm,
        )
        ctx.query_engine.stats.return_value.to_text.return_value = "5 entities"

        agent = PlanningAgent(context=ctx)
        reply = agent.chat("help me plan")

        assert reply == "I can help you plan."
        assert len(ctx.conversation_history) == 2  # user + assistant
        assert ctx.conversation_history[0]["role"] == "user"
        assert ctx.conversation_history[1]["role"] == "assistant"

    def test_chat_accumulates_history(self):
        from video_processor.agent.agent_loop import PlanningAgent

        mock_pm = MagicMock()
        mock_pm.chat.side_effect = ["reply1", "reply2"]

        ctx = AgentContext(provider_manager=mock_pm)
        agent = PlanningAgent(context=ctx)

        agent.chat("msg1")
        agent.chat("msg2")

        assert len(ctx.conversation_history) == 4  # 2 user + 2 assistant
        # The system message is constructed each time but not stored in history
        # Provider should receive progressively longer message lists
        second_call_messages = mock_pm.chat.call_args_list[1][0][0]
        # Should include system + 3 prior messages (user, assistant, user)
        assert len(second_call_messages) == 4  # system + user + assistant + user


# ---------------------------------------------------------------------------
# Orchestrator tests (from existing test_agent.py — kept for coverage)
# ---------------------------------------------------------------------------


class TestPlanCreation:
    def test_basic_plan(self):
        from video_processor.agent.orchestrator import AgentOrchestrator

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
        from video_processor.agent.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator()
        plan = agent._create_plan("test.mp4", "standard")
        steps = [s["step"] for s in plan]
        assert "detect_diagrams" in steps
        assert "build_knowledge_graph" in steps
        assert "deep_analysis" not in steps

    def test_comprehensive_plan(self):
        from video_processor.agent.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator()
        plan = agent._create_plan("test.mp4", "comprehensive")
        steps = [s["step"] for s in plan]
        assert "detect_diagrams" in steps
        assert "deep_analysis" in steps
        assert "cross_reference" in steps


class TestAdaptPlan:
    def test_adapts_for_long_transcript(self):
        from video_processor.agent.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator()
        agent._plan = [{"step": "generate_reports", "priority": "required"}]
        long_text = "word " * 3000
        agent._adapt_plan("transcribe", {"text": long_text})
        steps = [s["step"] for s in agent._plan]
        assert "deep_analysis" in steps

    def test_no_adapt_for_short_transcript(self):
        from video_processor.agent.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator()
        agent._plan = [{"step": "generate_reports", "priority": "required"}]
        agent._adapt_plan("transcribe", {"text": "Short text"})
        steps = [s["step"] for s in agent._plan]
        assert "deep_analysis" not in steps

    def test_adapts_for_many_diagrams(self):
        from video_processor.agent.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator()
        agent._plan = [{"step": "generate_reports", "priority": "required"}]
        diagrams = [MagicMock() for _ in range(5)]
        agent._adapt_plan("detect_diagrams", {"diagrams": diagrams, "captures": []})
        steps = [s["step"] for s in agent._plan]
        assert "cross_reference" in steps

    def test_insight_for_many_captures(self):
        from video_processor.agent.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator()
        agent._plan = []
        captures = [MagicMock() for _ in range(5)]
        diagrams = [MagicMock() for _ in range(2)]
        agent._adapt_plan("detect_diagrams", {"diagrams": diagrams, "captures": captures})
        assert len(agent._insights) == 1
        assert "uncertain frames" in agent._insights[0]

    def test_no_duplicate_steps(self):
        from video_processor.agent.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator()
        agent._plan = [{"step": "deep_analysis", "priority": "comprehensive"}]
        long_text = "word " * 3000
        agent._adapt_plan("transcribe", {"text": long_text})
        deep_steps = [s for s in agent._plan if s["step"] == "deep_analysis"]
        assert len(deep_steps) == 1


class TestFallbacks:
    def test_diagram_fallback(self):
        from video_processor.agent.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator()
        assert agent._get_fallback("detect_diagrams") == "screengrab_fallback"

    def test_no_fallback_for_unknown(self):
        from video_processor.agent.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator()
        assert agent._get_fallback("transcribe") is None


class TestInsights:
    def test_insights_property(self):
        from video_processor.agent.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator()
        agent._insights = ["Insight 1", "Insight 2"]
        assert agent.insights == ["Insight 1", "Insight 2"]
        agent.insights.append("should not modify internal")
        assert len(agent._insights) == 2

    def test_deep_analysis_populates_insights(self):
        from video_processor.agent.orchestrator import AgentOrchestrator

        pm = MagicMock()
        pm.chat.return_value = json.dumps(
            {
                "decisions": ["Decided to use microservices"],
                "risks": ["Timeline is tight"],
                "follow_ups": [],
                "tensions": [],
            }
        )
        agent = AgentOrchestrator(provider_manager=pm)
        agent._results["transcribe"] = {"text": "Some long transcript text here"}
        result = agent._deep_analysis("/tmp")
        assert "decisions" in result
        assert any("microservices" in i for i in agent._insights)
        assert any("Timeline" in i for i in agent._insights)

    def test_deep_analysis_handles_error(self):
        from video_processor.agent.orchestrator import AgentOrchestrator

        pm = MagicMock()
        pm.chat.side_effect = Exception("API error")
        agent = AgentOrchestrator(provider_manager=pm)
        agent._results["transcribe"] = {"text": "some text"}
        result = agent._deep_analysis("/tmp")
        assert result == {}

    def test_deep_analysis_no_transcript(self):
        from video_processor.agent.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator()
        agent._results["transcribe"] = {"text": ""}
        result = agent._deep_analysis("/tmp")
        assert result == {}


class TestBuildManifest:
    def test_builds_from_results(self):
        from video_processor.agent.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator()
        agent._results = {
            "extract_frames": {"frames": [1, 2, 3], "paths": ["/a.jpg", "/b.jpg"]},
            "extract_audio": {"audio_path": "/audio.wav", "properties": {"duration": 60.0}},
            "detect_diagrams": {"diagrams": [], "captures": []},
            "extract_key_points": {"key_points": []},
            "extract_action_items": {"action_items": []},
        }
        manifest = agent._build_manifest(Path("test.mp4"), Path("/out"), "Test", 5.0)
        assert manifest.video.title == "Test"
        assert manifest.stats.frames_extracted == 3
        assert manifest.stats.duration_seconds == 5.0
        assert manifest.video.duration_seconds == 60.0

    def test_handles_missing_results(self):
        from video_processor.agent.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator()
        agent._results = {}
        manifest = agent._build_manifest(Path("test.mp4"), Path("/out"), None, 1.0)
        assert manifest.video.title == "Analysis of test"
        assert manifest.stats.frames_extracted == 0

    def test_handles_error_results(self):
        from video_processor.agent.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator()
        agent._results = {
            "extract_frames": {"error": "failed"},
            "detect_diagrams": {"error": "also failed"},
        }
        manifest = agent._build_manifest(Path("vid.mp4"), Path("/out"), None, 2.0)
        assert manifest.stats.frames_extracted == 0
        assert len(manifest.diagrams) == 0
