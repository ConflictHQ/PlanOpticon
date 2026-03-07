"""Tests for agent skill execute() methods with mocked context."""

import json
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from video_processor.agent.skills.base import (
    AgentContext,
    Artifact,
    _skills,
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


@dataclass
class FakeEntity:
    name: str
    type: str

    def __str__(self):
        return self.name


class FakeQueryResult:
    """Mimics QueryResult.to_text()."""

    def __init__(self, text="Stats: 10 entities, 5 relationships"):
        self._text = text

    def to_text(self):
        return self._text


def _make_context(
    chat_response="# Generated Content\n\nSome markdown content.",
    planning_entities=None,
):
    """Build an AgentContext with mocked query_engine and provider_manager."""
    ctx = AgentContext()

    qe = MagicMock()
    qe.stats.return_value = FakeQueryResult("Stats: 10 entities, 5 rels")
    qe.entities.return_value = FakeQueryResult("Entity1, Entity2")
    qe.relationships.return_value = FakeQueryResult("Entity1 -> Entity2")
    ctx.query_engine = qe

    pm = MagicMock()
    pm.chat.return_value = chat_response
    ctx.provider_manager = pm

    ctx.knowledge_graph = MagicMock()

    if planning_entities is not None:
        ctx.planning_entities = planning_entities
    else:
        ctx.planning_entities = [
            FakeEntity(name="Auth system", type="feature"),
            FakeEntity(name="Launch v1", type="milestone"),
            FakeEntity(name="Must be fast", type="constraint"),
            FakeEntity(name="Build dashboard", type="goal"),
            FakeEntity(name="API depends on auth", type="dependency"),
            FakeEntity(name="User login", type="requirement"),
        ]

    return ctx


# ---------------------------------------------------------------------------
# ProjectPlanSkill
# ---------------------------------------------------------------------------


class TestProjectPlanSkill:
    def test_execute_returns_artifact(self):
        from video_processor.agent.skills.project_plan import ProjectPlanSkill

        skill = ProjectPlanSkill()
        ctx = _make_context()
        artifact = skill.execute(ctx)

        assert isinstance(artifact, Artifact)
        assert artifact.artifact_type == "project_plan"
        assert artifact.format == "markdown"
        assert len(artifact.content) > 0

    def test_execute_calls_provider(self):
        from video_processor.agent.skills.project_plan import ProjectPlanSkill

        skill = ProjectPlanSkill()
        ctx = _make_context()
        skill.execute(ctx)

        ctx.provider_manager.chat.assert_called_once()
        call_args = ctx.provider_manager.chat.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_execute_queries_graph(self):
        from video_processor.agent.skills.project_plan import ProjectPlanSkill

        skill = ProjectPlanSkill()
        ctx = _make_context()
        skill.execute(ctx)

        ctx.query_engine.stats.assert_called_once()
        ctx.query_engine.entities.assert_called_once()
        ctx.query_engine.relationships.assert_called_once()


# ---------------------------------------------------------------------------
# PRDSkill
# ---------------------------------------------------------------------------


class TestPRDSkill:
    def test_execute_returns_artifact(self):
        from video_processor.agent.skills.prd import PRDSkill

        skill = PRDSkill()
        ctx = _make_context()
        artifact = skill.execute(ctx)

        assert isinstance(artifact, Artifact)
        assert artifact.artifact_type == "prd"
        assert artifact.format == "markdown"

    def test_execute_filters_relevant_entities(self):
        from video_processor.agent.skills.prd import PRDSkill

        skill = PRDSkill()
        ctx = _make_context()
        skill.execute(ctx)

        # Should still call provider
        ctx.provider_manager.chat.assert_called_once()

    def test_execute_with_no_relevant_entities(self):
        from video_processor.agent.skills.prd import PRDSkill

        skill = PRDSkill()
        ctx = _make_context(
            planning_entities=[
                FakeEntity(name="Some goal", type="goal"),
            ]
        )
        artifact = skill.execute(ctx)

        assert isinstance(artifact, Artifact)
        assert artifact.artifact_type == "prd"


# ---------------------------------------------------------------------------
# RoadmapSkill
# ---------------------------------------------------------------------------


class TestRoadmapSkill:
    def test_execute_returns_artifact(self):
        from video_processor.agent.skills.roadmap import RoadmapSkill

        skill = RoadmapSkill()
        ctx = _make_context()
        artifact = skill.execute(ctx)

        assert isinstance(artifact, Artifact)
        assert artifact.artifact_type == "roadmap"
        assert artifact.format == "markdown"

    def test_execute_with_no_relevant_entities(self):
        from video_processor.agent.skills.roadmap import RoadmapSkill

        skill = RoadmapSkill()
        ctx = _make_context(
            planning_entities=[
                FakeEntity(name="Some constraint", type="constraint"),
            ]
        )
        artifact = skill.execute(ctx)

        assert isinstance(artifact, Artifact)


# ---------------------------------------------------------------------------
# TaskBreakdownSkill
# ---------------------------------------------------------------------------


class TestTaskBreakdownSkill:
    def test_execute_returns_artifact_json(self):
        from video_processor.agent.skills.task_breakdown import TaskBreakdownSkill

        tasks_json = json.dumps(
            [
                {
                    "id": "T1",
                    "title": "Setup",
                    "description": "Init",
                    "depends_on": [],
                    "priority": "high",
                    "estimate": "1d",
                    "assignee_role": "dev",
                },
            ]
        )
        skill = TaskBreakdownSkill()
        ctx = _make_context(chat_response=tasks_json)
        artifact = skill.execute(ctx)

        assert isinstance(artifact, Artifact)
        assert artifact.artifact_type == "task_list"
        assert artifact.format == "json"
        assert "tasks" in artifact.metadata
        assert len(artifact.metadata["tasks"]) == 1

    def test_execute_with_non_json_response(self):
        from video_processor.agent.skills.task_breakdown import TaskBreakdownSkill

        skill = TaskBreakdownSkill()
        ctx = _make_context(chat_response="Not valid JSON at all")
        artifact = skill.execute(ctx)

        assert isinstance(artifact, Artifact)
        assert artifact.artifact_type == "task_list"

    def test_execute_with_no_relevant_entities(self):
        from video_processor.agent.skills.task_breakdown import TaskBreakdownSkill

        tasks_json = json.dumps([])
        skill = TaskBreakdownSkill()
        ctx = _make_context(
            chat_response=tasks_json,
            planning_entities=[FakeEntity(name="X", type="constraint")],
        )
        artifact = skill.execute(ctx)
        assert artifact.metadata["tasks"] == []


# ---------------------------------------------------------------------------
# DocGeneratorSkill
# ---------------------------------------------------------------------------


class TestDocGeneratorSkill:
    def test_execute_default_type(self):
        from video_processor.agent.skills.doc_generator import DocGeneratorSkill

        skill = DocGeneratorSkill()
        ctx = _make_context()
        artifact = skill.execute(ctx)

        assert isinstance(artifact, Artifact)
        assert artifact.artifact_type == "document"
        assert artifact.format == "markdown"
        assert artifact.metadata["doc_type"] == "technical_doc"

    def test_execute_adr_type(self):
        from video_processor.agent.skills.doc_generator import DocGeneratorSkill

        skill = DocGeneratorSkill()
        ctx = _make_context()
        artifact = skill.execute(ctx, doc_type="adr")

        assert artifact.metadata["doc_type"] == "adr"

    def test_execute_meeting_notes_type(self):
        from video_processor.agent.skills.doc_generator import DocGeneratorSkill

        skill = DocGeneratorSkill()
        ctx = _make_context()
        artifact = skill.execute(ctx, doc_type="meeting_notes")

        assert artifact.metadata["doc_type"] == "meeting_notes"

    def test_execute_unknown_type_falls_back(self):
        from video_processor.agent.skills.doc_generator import DocGeneratorSkill

        skill = DocGeneratorSkill()
        ctx = _make_context()
        artifact = skill.execute(ctx, doc_type="unknown_type")

        # Falls back to technical_doc prompt
        assert artifact.artifact_type == "document"


# ---------------------------------------------------------------------------
# RequirementsChatSkill
# ---------------------------------------------------------------------------


class TestRequirementsChatSkill:
    def test_execute_returns_artifact(self):
        from video_processor.agent.skills.requirements_chat import RequirementsChatSkill

        questions = {
            "questions": [
                {"id": "Q1", "category": "goals", "question": "What?", "context": "Why"},
            ]
        }
        skill = RequirementsChatSkill()
        ctx = _make_context(chat_response=json.dumps(questions))
        artifact = skill.execute(ctx)

        assert isinstance(artifact, Artifact)
        assert artifact.artifact_type == "requirements"
        assert artifact.format == "json"
        assert artifact.metadata["stage"] == "questionnaire"

    def test_gather_requirements(self):
        from video_processor.agent.skills.requirements_chat import RequirementsChatSkill

        reqs = {
            "goals": ["Build auth"],
            "constraints": ["Budget < 10k"],
            "priorities": ["Security"],
            "scope": {"in_scope": ["Login"], "out_of_scope": ["SSO"]},
        }
        skill = RequirementsChatSkill()
        ctx = _make_context(chat_response=json.dumps(reqs))
        result = skill.gather_requirements(ctx, {"Q1": "We need auth", "Q2": "Budget is limited"})

        assert isinstance(result, dict)

    def test_gather_requirements_non_json_response(self):
        from video_processor.agent.skills.requirements_chat import RequirementsChatSkill

        skill = RequirementsChatSkill()
        ctx = _make_context(chat_response="Not JSON")
        result = skill.gather_requirements(ctx, {"Q1": "answer"})

        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Skill metadata
# ---------------------------------------------------------------------------


class TestSkillMetadata:
    def test_project_plan_name(self):
        from video_processor.agent.skills.project_plan import ProjectPlanSkill

        assert ProjectPlanSkill.name == "project_plan"

    def test_prd_name(self):
        from video_processor.agent.skills.prd import PRDSkill

        assert PRDSkill.name == "prd"

    def test_roadmap_name(self):
        from video_processor.agent.skills.roadmap import RoadmapSkill

        assert RoadmapSkill.name == "roadmap"

    def test_task_breakdown_name(self):
        from video_processor.agent.skills.task_breakdown import TaskBreakdownSkill

        assert TaskBreakdownSkill.name == "task_breakdown"

    def test_doc_generator_name(self):
        from video_processor.agent.skills.doc_generator import DocGeneratorSkill

        assert DocGeneratorSkill.name == "doc_generator"

    def test_requirements_chat_name(self):
        from video_processor.agent.skills.requirements_chat import RequirementsChatSkill

        assert RequirementsChatSkill.name == "requirements_chat"

    def test_can_execute_with_context(self):
        from video_processor.agent.skills.project_plan import ProjectPlanSkill

        skill = ProjectPlanSkill()
        ctx = _make_context()
        assert skill.can_execute(ctx) is True

    def test_can_execute_without_kg(self):
        from video_processor.agent.skills.project_plan import ProjectPlanSkill

        skill = ProjectPlanSkill()
        ctx = _make_context()
        ctx.knowledge_graph = None
        assert skill.can_execute(ctx) is False

    def test_can_execute_without_provider(self):
        from video_processor.agent.skills.project_plan import ProjectPlanSkill

        skill = ProjectPlanSkill()
        ctx = _make_context()
        ctx.provider_manager = None
        assert skill.can_execute(ctx) is False
