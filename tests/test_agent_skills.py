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


# ---------------------------------------------------------------------------
# WikiGeneratorSkill
# ---------------------------------------------------------------------------


class TestWikiGeneratorSkill:
    def _sample_kg_data(self):
        return {
            "nodes": [
                {
                    "name": "Python",
                    "type": "technology",
                    "descriptions": ["A programming language"],
                },
                {
                    "name": "Alice",
                    "type": "person",
                    "descriptions": ["Lead developer"],
                },
                {
                    "name": "FastAPI",
                    "type": "technology",
                    "descriptions": ["Web framework"],
                },
            ],
            "relationships": [
                {"source": "Alice", "target": "Python", "type": "uses"},
                {"source": "FastAPI", "target": "Python", "type": "built_with"},
            ],
        }

    def test_generate_wiki(self):
        from video_processor.agent.skills.wiki_generator import generate_wiki

        pages = generate_wiki(self._sample_kg_data(), title="Test Wiki")

        assert "Home" in pages
        assert "_Sidebar" in pages
        assert "Test Wiki" in pages["Home"]
        assert "3" in pages["Home"]  # 3 entities
        assert "2" in pages["Home"]  # 2 relationships

        # Entity pages should exist
        assert "Python" in pages
        assert "Alice" in pages
        assert "FastAPI" in pages

        # Type index pages should exist
        assert "Technology" in pages
        assert "Person" in pages

        # Alice's page should reference Python
        assert "Python" in pages["Alice"]
        assert "uses" in pages["Alice"]

    def test_generate_wiki_with_artifacts(self):
        from video_processor.agent.skills.wiki_generator import generate_wiki

        art = Artifact(
            name="Project Plan",
            content="# Plan\n\nDo the thing.",
            artifact_type="project_plan",
            format="markdown",
        )
        pages = generate_wiki(self._sample_kg_data(), artifacts=[art])

        assert "Project-Plan" in pages
        assert "Do the thing." in pages["Project-Plan"]
        assert "Planning Artifacts" in pages["Home"]

    def test_write_wiki(self, tmp_path):
        from video_processor.agent.skills.wiki_generator import write_wiki

        pages = {
            "Home": "# Home\n\nWelcome.",
            "Page-One": "# Page One\n\nContent.",
        }
        paths = write_wiki(pages, tmp_path / "wiki")

        assert len(paths) == 2
        assert (tmp_path / "wiki" / "Home.md").exists()
        assert (tmp_path / "wiki" / "Page-One.md").exists()
        assert "Welcome." in (tmp_path / "wiki" / "Home.md").read_text()

    def test_sanitize_filename(self):
        from video_processor.agent.skills.wiki_generator import _sanitize_filename

        assert _sanitize_filename("Hello World") == "Hello-World"
        assert _sanitize_filename("path/to\\file") == "path-to-file"
        assert _sanitize_filename("version.2") == "version-2"

    def test_wiki_link(self):
        from video_processor.agent.skills.wiki_generator import _wiki_link

        result = _wiki_link("My Page")
        assert result == "[My Page](My-Page)"

        result = _wiki_link("Simple")
        assert result == "[Simple](Simple)"


# ---------------------------------------------------------------------------
# NotesExportSkill
# ---------------------------------------------------------------------------


class TestNotesExportSkill:
    def _sample_kg_data(self):
        return {
            "nodes": [
                {
                    "name": "Python",
                    "type": "technology",
                    "descriptions": ["A programming language"],
                },
                {
                    "name": "Alice",
                    "type": "person",
                    "descriptions": ["Lead developer"],
                },
            ],
            "relationships": [
                {"source": "Alice", "target": "Python", "type": "uses"},
            ],
        }

    def test_export_to_obsidian(self, tmp_path):
        from video_processor.agent.skills.notes_export import export_to_obsidian

        output_dir = tmp_path / "obsidian_vault"
        export_to_obsidian(self._sample_kg_data(), output_dir)

        assert output_dir.is_dir()

        # Check entity files exist
        python_file = output_dir / "Python.md"
        alice_file = output_dir / "Alice.md"
        assert python_file.exists()
        assert alice_file.exists()

        # Check frontmatter in entity file
        python_content = python_file.read_text()
        assert "---" in python_content
        assert "type: technology" in python_content
        assert "# Python" in python_content

        # Check wiki-links in Alice file
        alice_content = alice_file.read_text()
        assert "[[Python]]" in alice_content
        assert "uses" in alice_content

        # Check index file
        index_file = output_dir / "_Index.md"
        assert index_file.exists()
        index_content = index_file.read_text()
        assert "[[Python]]" in index_content
        assert "[[Alice]]" in index_content

    def test_export_to_obsidian_with_artifacts(self, tmp_path):
        from video_processor.agent.skills.notes_export import export_to_obsidian

        art = Artifact(
            name="Test Plan",
            content="# Plan\n\nSteps here.",
            artifact_type="project_plan",
            format="markdown",
        )
        output_dir = tmp_path / "obsidian_arts"
        export_to_obsidian(self._sample_kg_data(), output_dir, artifacts=[art])

        art_file = output_dir / "Test Plan.md"
        assert art_file.exists()
        art_content = art_file.read_text()
        assert "artifact" in art_content
        assert "Steps here." in art_content

    def test_export_to_notion_md(self, tmp_path):
        from video_processor.agent.skills.notes_export import export_to_notion_md

        output_dir = tmp_path / "notion_export"
        export_to_notion_md(self._sample_kg_data(), output_dir)

        assert output_dir.is_dir()

        # Check CSV database file
        csv_file = output_dir / "entities_database.csv"
        assert csv_file.exists()
        csv_content = csv_file.read_text()
        assert "Name" in csv_content
        assert "Type" in csv_content
        assert "Python" in csv_content
        assert "Alice" in csv_content

        # Check entity markdown files
        python_file = output_dir / "Python.md"
        assert python_file.exists()
        python_content = python_file.read_text()
        assert "# Python" in python_content
        assert "technology" in python_content

        # Check overview file
        overview_file = output_dir / "Overview.md"
        assert overview_file.exists()

    def test_export_to_notion_md_with_artifacts(self, tmp_path):
        from video_processor.agent.skills.notes_export import export_to_notion_md

        art = Artifact(
            name="Roadmap",
            content="# Roadmap\n\nQ1 goals.",
            artifact_type="roadmap",
            format="markdown",
        )
        output_dir = tmp_path / "notion_arts"
        export_to_notion_md(self._sample_kg_data(), output_dir, artifacts=[art])

        art_file = output_dir / "Roadmap.md"
        assert art_file.exists()
        art_content = art_file.read_text()
        assert "Q1 goals." in art_content
