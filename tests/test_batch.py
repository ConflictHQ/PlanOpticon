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


class TestKnowledgeGraphMerge:
    def test_merge_new_nodes(self):
        kg1 = KnowledgeGraph()
        kg1.nodes["Python"] = {
            "id": "Python",
            "name": "Python",
            "type": "concept",
            "descriptions": {"A programming language"},
            "occurrences": [{"source": "video1"}],
        }

        kg2 = KnowledgeGraph()
        kg2.nodes["Rust"] = {
            "id": "Rust",
            "name": "Rust",
            "type": "concept",
            "descriptions": {"A systems language"},
            "occurrences": [{"source": "video2"}],
        }

        kg1.merge(kg2)
        assert "Python" in kg1.nodes
        assert "Rust" in kg1.nodes
        assert len(kg1.nodes) == 2

    def test_merge_overlapping_nodes_case_insensitive(self):
        kg1 = KnowledgeGraph()
        kg1.nodes["Python"] = {
            "id": "Python",
            "name": "Python",
            "type": "concept",
            "descriptions": {"Language A"},
            "occurrences": [{"source": "v1"}],
        }

        kg2 = KnowledgeGraph()
        kg2.nodes["python"] = {
            "id": "python",
            "name": "python",
            "type": "concept",
            "descriptions": {"Language B"},
            "occurrences": [{"source": "v2"}],
        }

        kg1.merge(kg2)
        # Should merge into existing node, not create duplicate
        assert len(kg1.nodes) == 1
        assert "Python" in kg1.nodes
        assert len(kg1.nodes["Python"]["occurrences"]) == 2
        assert "Language B" in kg1.nodes["Python"]["descriptions"]

    def test_merge_relationships(self):
        kg1 = KnowledgeGraph()
        kg1.relationships = [{"source": "A", "target": "B", "type": "uses"}]

        kg2 = KnowledgeGraph()
        kg2.relationships = [{"source": "C", "target": "D", "type": "calls"}]

        kg1.merge(kg2)
        assert len(kg1.relationships) == 2

    def test_merge_empty_into_populated(self):
        kg1 = KnowledgeGraph()
        kg1.nodes["X"] = {
            "id": "X",
            "name": "X",
            "type": "concept",
            "descriptions": set(),
            "occurrences": [],
        }
        kg2 = KnowledgeGraph()
        kg1.merge(kg2)
        assert len(kg1.nodes) == 1


class TestKnowledgeGraphFromDict:
    def test_round_trip(self):
        kg = KnowledgeGraph()
        kg.nodes["Alice"] = {
            "id": "Alice",
            "name": "Alice",
            "type": "person",
            "descriptions": {"Team lead"},
            "occurrences": [{"source": "transcript"}],
        }
        kg.relationships = [{"source": "Alice", "target": "Bob", "type": "manages"}]

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
        kg.nodes["Test"] = {
            "id": "Test",
            "name": "Test",
            "type": "concept",
            "descriptions": {"A test entity"},
            "occurrences": [],
        }
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
        kg.nodes["Test"] = {
            "id": "Test",
            "name": "Test",
            "type": "concept",
            "descriptions": set(),
            "occurrences": [],
        }
        kg.relationships = [{"source": "Test", "target": "Test", "type": "self"}]

        gen = PlanGenerator()
        summary = gen.generate_batch_summary(
            manifests=manifests, kg=kg, output_path=tmp_path / "s.md"
        )
        assert "Knowledge Graph" in summary
        assert "mermaid" in summary
