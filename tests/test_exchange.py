"""Tests for the PlanOpticonExchange interchange format."""

import json

from video_processor.exchange import (
    ArtifactMeta,
    PlanOpticonExchange,
    ProjectMeta,
)
from video_processor.models import Entity, Relationship, SourceRecord

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _sample_entity(name: str = "Python", etype: str = "technology"):
    return Entity(
        name=name,
        type=etype,
        descriptions=["A programming language"],
    )


def _sample_relationship():
    return Relationship(
        source="Alice",
        target="Python",
        type="uses",
    )


def _sample_source():
    return SourceRecord(
        source_id="src-1",
        source_type="video",
        title="Intro recording",
    )


def _sample_artifact():
    return ArtifactMeta(
        name="roadmap",
        content="# Roadmap\n- Phase 1",
        artifact_type="roadmap",
        format="markdown",
    )


def _sample_project():
    return ProjectMeta(name="TestProject", description="A test")


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


def test_create_empty_exchange():
    ex = PlanOpticonExchange(project=_sample_project())
    assert ex.version == "1.0"
    assert ex.entities == []
    assert ex.relationships == []
    assert ex.artifacts == []
    assert ex.sources == []
    assert ex.project.name == "TestProject"


def test_create_with_data():
    ex = PlanOpticonExchange(
        project=_sample_project(),
        entities=[_sample_entity()],
        relationships=[_sample_relationship()],
        artifacts=[_sample_artifact()],
        sources=[_sample_source()],
    )
    assert len(ex.entities) == 1
    assert ex.entities[0].name == "Python"
    assert len(ex.relationships) == 1
    assert len(ex.artifacts) == 1
    assert len(ex.sources) == 1


def test_json_roundtrip(tmp_path):
    original = PlanOpticonExchange(
        project=_sample_project(),
        entities=[_sample_entity()],
        relationships=[_sample_relationship()],
        artifacts=[_sample_artifact()],
        sources=[_sample_source()],
    )
    out = tmp_path / "exchange.json"
    original.to_file(out)

    assert out.exists()
    loaded = PlanOpticonExchange.from_file(out)
    assert loaded.project.name == original.project.name
    assert len(loaded.entities) == 1
    assert loaded.entities[0].name == "Python"
    assert len(loaded.relationships) == 1
    assert len(loaded.artifacts) == 1
    assert len(loaded.sources) == 1

    # Verify valid JSON on disk
    raw = json.loads(out.read_text())
    assert raw["version"] == "1.0"


def test_json_schema_export():
    schema = PlanOpticonExchange.json_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema
    assert "version" in schema["properties"]
    assert "project" in schema["properties"]
    assert "entities" in schema["properties"]


def test_from_knowledge_graph():
    kg_dict = {
        "nodes": [
            {
                "id": "python",
                "name": "Python",
                "type": "technology",
                "descriptions": ["A language"],
                "occurrences": [],
            },
            {
                "id": "alice",
                "name": "Alice",
                "type": "person",
                "descriptions": ["Engineer"],
                "occurrences": [],
            },
        ],
        "relationships": [
            {
                "source": "Alice",
                "target": "Python",
                "type": "uses",
            },
        ],
        "sources": [
            {
                "source_id": "s1",
                "source_type": "video",
                "title": "Recording",
            },
        ],
    }

    ex = PlanOpticonExchange.from_knowledge_graph(
        kg_dict,
        project_name="Demo",
        tags=["test"],
    )
    assert ex.project.name == "Demo"
    assert len(ex.entities) == 2
    assert len(ex.relationships) == 1
    assert len(ex.sources) == 1
    assert "test" in ex.project.tags


def test_merge_deduplicates_entities():
    ex1 = PlanOpticonExchange(
        project=_sample_project(),
        entities=[_sample_entity("Python"), _sample_entity("Rust")],
        relationships=[_sample_relationship()],
        sources=[_sample_source()],
    )
    ex2 = PlanOpticonExchange(
        project=ProjectMeta(name="Other"),
        entities=[
            _sample_entity("Python"),  # duplicate
            _sample_entity("Go"),  # new
        ],
        relationships=[
            Relationship(source="Bob", target="Go", type="uses"),
        ],
        sources=[
            SourceRecord(
                source_id="src-2",
                source_type="document",
                title="Notes",
            ),
        ],
    )

    ex1.merge(ex2)

    entity_names = [e.name for e in ex1.entities]
    assert entity_names.count("Python") == 1
    assert "Go" in entity_names
    assert "Rust" in entity_names
    assert len(ex1.entities) == 3
    assert len(ex1.relationships) == 2
    assert len(ex1.sources) == 2


def test_version_field():
    ex = PlanOpticonExchange(
        version="2.0",
        project=_sample_project(),
    )
    assert ex.version == "2.0"


def test_artifact_meta_model():
    art = ArtifactMeta(
        name="plan",
        content="# Plan\nDo stuff",
        artifact_type="project_plan",
        format="markdown",
        metadata={"author": "agent"},
    )
    assert art.name == "plan"
    assert art.artifact_type == "project_plan"
    assert art.format == "markdown"
    assert art.metadata == {"author": "agent"}

    # Roundtrip via dict
    d = art.model_dump()
    restored = ArtifactMeta.model_validate(d)
    assert restored == art
