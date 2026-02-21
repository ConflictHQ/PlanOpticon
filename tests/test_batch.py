"""Tests for batch processing and knowledge graph merging."""

import json

from video_processor.integrators.knowledge_graph import KnowledgeGraph
from video_processor.integrators.plan_generator import PlanGenerator
from video_processor.models import (
    ActionItem,
    BatchManifest,
    BatchVideoEntry,
    DiagramResult,
    KeyPoint,
    VideoManifest,
    VideoMetadata,
)
from video_processor.output_structure import (
    create_batch_output_dirs,
    read_batch_manifest,
    write_batch_manifest,
)


def _make_kg_with_entity(name, entity_type="concept", descriptions=None, occurrences=None):
    """Helper to build a KnowledgeGraph with entities via the store API."""
    kg = KnowledgeGraph()
    descs = list(descriptions) if descriptions else []
    kg._store.merge_entity(name, entity_type, descs)
    for occ in occurrences or []:
        kg._store.add_occurrence(name, occ.get("source", ""), occ.get("timestamp"), occ.get("text"))
    return kg


class TestKnowledgeGraphMerge:
    def test_merge_new_nodes(self):
        kg1 = KnowledgeGraph()
        kg1._store.merge_entity("Python", "concept", ["A programming language"])
        kg1._store.add_occurrence("Python", "video1")

        kg2 = KnowledgeGraph()
        kg2._store.merge_entity("Rust", "concept", ["A systems language"])
        kg2._store.add_occurrence("Rust", "video2")

        kg1.merge(kg2)
        assert "Python" in kg1.nodes
        assert "Rust" in kg1.nodes
        assert len(kg1.nodes) == 2

    def test_merge_overlapping_nodes_case_insensitive(self):
        kg1 = KnowledgeGraph()
        kg1._store.merge_entity("Python", "concept", ["Language A"])
        kg1._store.add_occurrence("Python", "v1")

        kg2 = KnowledgeGraph()
        kg2._store.merge_entity("python", "concept", ["Language B"])
        kg2._store.add_occurrence("python", "v2")

        kg1.merge(kg2)
        # Should merge into existing node, not create duplicate
        assert len(kg1.nodes) == 1
        assert "Python" in kg1.nodes
        assert len(kg1.nodes["Python"]["occurrences"]) == 2
        assert "Language B" in kg1.nodes["Python"]["descriptions"]

    def test_merge_relationships(self):
        kg1 = KnowledgeGraph()
        kg1._store.merge_entity("A", "concept", [])
        kg1._store.merge_entity("B", "concept", [])
        kg1._store.add_relationship("A", "B", "uses")

        kg2 = KnowledgeGraph()
        kg2._store.merge_entity("C", "concept", [])
        kg2._store.merge_entity("D", "concept", [])
        kg2._store.add_relationship("C", "D", "calls")

        kg1.merge(kg2)
        assert len(kg1.relationships) == 2

    def test_merge_empty_into_populated(self):
        kg1 = KnowledgeGraph()
        kg1._store.merge_entity("X", "concept", [])

        kg2 = KnowledgeGraph()
        kg1.merge(kg2)
        assert len(kg1.nodes) == 1


class TestKnowledgeGraphFromDict:
    def test_round_trip(self):
        kg = KnowledgeGraph()
        kg._store.merge_entity("Alice", "person", ["Team lead"])
        kg._store.add_occurrence("Alice", "transcript")
        kg._store.merge_entity("Bob", "person", [])
        kg._store.add_relationship("Alice", "Bob", "manages")

        data = kg.to_dict()
        restored = KnowledgeGraph.from_dict(data)
        assert "Alice" in restored.nodes
        assert restored.nodes["Alice"]["type"] == "person"
        assert len(restored.relationships) == 1

    def test_from_dict_with_list_descriptions(self):
        data = {
            "nodes": [
                {
                    "id": "X",
                    "name": "X",
                    "type": "concept",
                    "descriptions": ["desc1", "desc2"],
                    "occurrences": [],
                }
            ],
            "relationships": [],
        }
        kg = KnowledgeGraph.from_dict(data)
        assert "X" in kg.nodes
        assert "desc1" in kg.nodes["X"]["descriptions"]

    def test_from_empty_dict(self):
        kg = KnowledgeGraph.from_dict({})
        assert len(kg.nodes) == 0
        assert len(kg.relationships) == 0


class TestKnowledgeGraphSave:
    def test_save_as_pydantic(self, tmp_path):
        kg = KnowledgeGraph()
        kg._store.merge_entity("Test", "concept", ["A test entity"])

        path = kg.save(tmp_path / "kg.json")
        assert path.exists()
        data = json.loads(path.read_text())
        assert "nodes" in data
        assert data["nodes"][0]["name"] == "Test"


class TestBatchOutputDirs:
    def test_creates_video_dirs(self, tmp_path):
        dirs = create_batch_output_dirs(tmp_path / "batch", "test_batch")
        assert dirs["root"].exists()
        assert dirs["videos"].exists()


class TestBatchManifest:
    def test_round_trip(self, tmp_path):
        manifest = BatchManifest(
            title="Test Batch",
            total_videos=2,
            completed_videos=1,
            failed_videos=1,
            videos=[
                BatchVideoEntry(
                    video_name="v1",
                    manifest_path="videos/v1/manifest.json",
                    status="completed",
                    diagrams_count=3,
                ),
                BatchVideoEntry(
                    video_name="v2",
                    manifest_path="videos/v2/manifest.json",
                    status="failed",
                    error="Audio extraction failed",
                ),
            ],
        )
        write_batch_manifest(manifest, tmp_path)
        restored = read_batch_manifest(tmp_path)
        assert restored.title == "Test Batch"
        assert restored.total_videos == 2
        assert restored.videos[0].status == "completed"
        assert restored.videos[1].error == "Audio extraction failed"


class TestBatchSummary:
    def test_generate_batch_summary(self, tmp_path):
        manifests = [
            VideoManifest(
                video=VideoMetadata(title="Meeting 1", duration_seconds=3600),
                key_points=[KeyPoint(point="Point 1")],
                action_items=[ActionItem(action="Do X", assignee="Alice")],
                diagrams=[DiagramResult(frame_index=0, confidence=0.9)],
            ),
            VideoManifest(
                video=VideoMetadata(title="Meeting 2"),
                key_points=[KeyPoint(point="Point 2"), KeyPoint(point="Point 3")],
                action_items=[],
                diagrams=[],
            ),
        ]

        gen = PlanGenerator()
        summary = gen.generate_batch_summary(
            manifests=manifests,
            title="Weekly Meetings",
            output_path=tmp_path / "summary.md",
        )

        assert "Weekly Meetings" in summary
        assert "2" in summary  # 2 videos
        assert "Meeting 1" in summary
        assert "Meeting 2" in summary
        assert "Do X" in summary
        assert "Alice" in summary
        assert (tmp_path / "summary.md").exists()

    def test_batch_summary_with_kg(self, tmp_path):
        manifests = [
            VideoManifest(video=VideoMetadata(title="V1")),
        ]
        kg = KnowledgeGraph()
        kg._store.merge_entity("Test", "concept", [])
        kg._store.add_relationship("Test", "Test", "self")

        gen = PlanGenerator()
        summary = gen.generate_batch_summary(
            manifests=manifests, kg=kg, output_path=tmp_path / "s.md"
        )
        assert "Knowledge Graph" in summary
        assert "mermaid" in summary
