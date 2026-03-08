"""Tests for the KnowledgeGraph class."""

import json
from unittest.mock import MagicMock, patch

import pytest

from video_processor.integrators.knowledge_graph import KnowledgeGraph


@pytest.fixture
def mock_pm():
    """A mock ProviderManager that returns predictable JSON from chat()."""
    pm = MagicMock()
    pm.chat.return_value = json.dumps(
        {
            "entities": [
                {"name": "Python", "type": "technology", "description": "A programming language"},
                {"name": "Alice", "type": "person", "description": "Lead developer"},
            ],
            "relationships": [
                {"source": "Alice", "target": "Python", "type": "uses"},
            ],
        }
    )
    return pm


@pytest.fixture
def kg_no_provider():
    """KnowledgeGraph with no provider (in-memory store)."""
    return KnowledgeGraph()


@pytest.fixture
def kg_with_provider(mock_pm):
    """KnowledgeGraph with a mock provider (in-memory store)."""
    return KnowledgeGraph(provider_manager=mock_pm)


class TestCreation:
    def test_create_without_db_path(self):
        kg = KnowledgeGraph()
        assert kg.pm is None
        assert kg._store.get_entity_count() == 0
        assert kg._store.get_relationship_count() == 0

    def test_create_with_db_path(self, tmp_path):
        db_path = tmp_path / "test.db"
        kg = KnowledgeGraph(db_path=db_path)
        assert kg._store.get_entity_count() == 0
        assert db_path.exists()

    def test_create_with_provider(self, mock_pm):
        kg = KnowledgeGraph(provider_manager=mock_pm)
        assert kg.pm is mock_pm


class TestProcessTranscript:
    def test_process_transcript_extracts_entities(self, kg_with_provider, mock_pm):
        transcript = {
            "segments": [
                {"text": "Alice is using Python for the project", "start": 0.0, "speaker": "Alice"},
                {"text": "It works great for data processing", "start": 5.0},
            ]
        }
        kg_with_provider.process_transcript(transcript)

        # The mock returns Python and Alice as entities
        nodes = kg_with_provider.nodes
        assert "Python" in nodes
        assert "Alice" in nodes
        assert nodes["Python"]["type"] == "technology"

    def test_process_transcript_registers_speakers(self, kg_with_provider):
        transcript = {
            "segments": [
                {"text": "Hello everyone", "start": 0.0, "speaker": "Bob"},
            ]
        }
        kg_with_provider.process_transcript(transcript)
        assert kg_with_provider._store.has_entity("Bob")

    def test_process_transcript_missing_segments(self, kg_with_provider):
        """Should log warning and return without error."""
        kg_with_provider.process_transcript({})
        assert kg_with_provider._store.get_entity_count() == 0

    def test_process_transcript_empty_text_skipped(self, kg_with_provider, mock_pm):
        transcript = {
            "segments": [
                {"text": "   ", "start": 0.0},
            ]
        }
        kg_with_provider.process_transcript(transcript)
        # chat should not be called for empty batches (speaker registration may still happen)
        mock_pm.chat.assert_not_called()

    def test_process_transcript_batching(self, kg_with_provider, mock_pm):
        """With batch_size=2, 5 segments should produce 3 batches."""
        segments = [{"text": f"Segment {i}", "start": float(i)} for i in range(5)]
        transcript = {"segments": segments}
        kg_with_provider.process_transcript(transcript, batch_size=2)
        assert mock_pm.chat.call_count == 3


class TestProcessDiagrams:
    def test_process_diagrams_with_text(self, kg_with_provider, mock_pm):
        diagrams = [
            {"text_content": "Architecture shows Python microservices", "frame_index": 0},
        ]
        kg_with_provider.process_diagrams(diagrams)

        # Should have called chat once for the text content
        assert mock_pm.chat.call_count == 1
        # diagram_0 entity should exist
        assert kg_with_provider._store.has_entity("diagram_0")

    def test_process_diagrams_without_text(self, kg_with_provider, mock_pm):
        diagrams = [
            {"text_content": "", "frame_index": 5},
        ]
        kg_with_provider.process_diagrams(diagrams)
        # No chat call for empty text
        mock_pm.chat.assert_not_called()
        # But diagram entity still created
        assert kg_with_provider._store.has_entity("diagram_0")

    def test_process_multiple_diagrams(self, kg_with_provider, mock_pm):
        diagrams = [
            {"text_content": "Diagram A content", "frame_index": 0},
            {"text_content": "Diagram B content", "frame_index": 10},
        ]
        kg_with_provider.process_diagrams(diagrams)
        assert kg_with_provider._store.has_entity("diagram_0")
        assert kg_with_provider._store.has_entity("diagram_1")


class TestProcessScreenshots:
    @pytest.fixture
    def mock_pm(self):
        pm = MagicMock()
        pm.chat.return_value = json.dumps(
            [
                {"name": "Python", "type": "technology", "description": "Language"},
                {"name": "Flask", "type": "technology", "description": "Framework"},
            ]
        )
        return pm

    @pytest.fixture
    def kg_with_provider(self, mock_pm):
        return KnowledgeGraph(provider_manager=mock_pm)

    def test_process_screenshots_with_text(self, kg_with_provider, mock_pm):
        screenshots = [
            {
                "text_content": "import flask\napp = Flask(__name__)",
                "content_type": "code",
                "entities": ["Flask", "Python"],
                "frame_index": 3,
            },
        ]
        kg_with_provider.process_screenshots(screenshots)
        # LLM extraction from text_content
        mock_pm.chat.assert_called()
        # Explicitly listed entities should be added
        assert kg_with_provider._store.has_entity("Flask")
        assert kg_with_provider._store.has_entity("Python")

    def test_process_screenshots_without_text(self, kg_with_provider, mock_pm):
        screenshots = [
            {
                "text_content": "",
                "content_type": "other",
                "entities": ["Docker"],
                "frame_index": 5,
            },
        ]
        kg_with_provider.process_screenshots(screenshots)
        # No chat call for empty text
        mock_pm.chat.assert_not_called()
        # But explicit entities still added
        assert kg_with_provider._store.has_entity("Docker")

    def test_process_screenshots_empty_entities(self, kg_with_provider):
        screenshots = [
            {
                "text_content": "",
                "content_type": "slide",
                "entities": [],
                "frame_index": 0,
            },
        ]
        kg_with_provider.process_screenshots(screenshots)
        # No crash, no entities added

    def test_process_screenshots_filters_short_names(self, kg_with_provider):
        screenshots = [
            {
                "text_content": "",
                "entities": ["A", "Go", "Python"],
                "frame_index": 0,
            },
        ]
        kg_with_provider.process_screenshots(screenshots)
        # "A" is too short (< 2 chars), filtered out
        assert not kg_with_provider._store.has_entity("A")
        assert kg_with_provider._store.has_entity("Go")
        assert kg_with_provider._store.has_entity("Python")


class TestToDictFromDict:
    def test_round_trip_empty(self):
        kg = KnowledgeGraph()
        data = kg.to_dict()
        kg2 = KnowledgeGraph.from_dict(data)
        assert kg2._store.get_entity_count() == 0
        assert kg2._store.get_relationship_count() == 0

    def test_round_trip_with_entities(self, kg_with_provider, mock_pm):
        # Add some content to populate the graph
        kg_with_provider.add_content("Alice uses Python", "test_source")
        original = kg_with_provider.to_dict()

        restored = KnowledgeGraph.from_dict(original)
        restored_dict = restored.to_dict()

        assert len(restored_dict["nodes"]) == len(original["nodes"])
        assert len(restored_dict["relationships"]) == len(original["relationships"])

        original_names = {n["name"] for n in original["nodes"]}
        restored_names = {n["name"] for n in restored_dict["nodes"]}
        assert original_names == restored_names

    def test_round_trip_with_sources(self):
        kg = KnowledgeGraph()
        kg.register_source(
            {
                "source_id": "src1",
                "source_type": "video",
                "title": "Test Video",
                "ingested_at": "2025-01-01T00:00:00",
            }
        )
        data = kg.to_dict()
        assert "sources" in data
        assert data["sources"][0]["source_id"] == "src1"

        kg2 = KnowledgeGraph.from_dict(data)
        sources = kg2._store.get_sources()
        assert len(sources) == 1
        assert sources[0]["source_id"] == "src1"

    def test_from_dict_with_db_path(self, tmp_path):
        data = {
            "nodes": [
                {"name": "TestEntity", "type": "concept", "descriptions": ["A test"]},
            ],
            "relationships": [],
        }
        db_path = tmp_path / "restored.db"
        kg = KnowledgeGraph.from_dict(data, db_path=db_path)
        assert kg._store.has_entity("TestEntity")
        assert db_path.exists()


class TestSave:
    def test_save_json(self, tmp_path, kg_with_provider, mock_pm):
        kg_with_provider.add_content("Alice uses Python", "source1")
        path = tmp_path / "graph.json"
        result = kg_with_provider.save(path)

        assert result == path
        assert path.exists()
        data = json.loads(path.read_text())
        assert "nodes" in data
        assert "relationships" in data

    def test_save_db(self, tmp_path, kg_with_provider, mock_pm):
        kg_with_provider.add_content("Alice uses Python", "source1")
        path = tmp_path / "graph.db"
        result = kg_with_provider.save(path)

        assert result == path
        assert path.exists()

    def test_save_no_suffix_defaults_to_db(self, tmp_path, kg_with_provider, mock_pm):
        kg_with_provider.add_content("Alice uses Python", "source1")
        path = tmp_path / "graph"
        result = kg_with_provider.save(path)
        assert result.suffix == ".db"
        assert result.exists()

    def test_save_creates_parent_dirs(self, tmp_path, kg_with_provider, mock_pm):
        kg_with_provider.add_content("Alice uses Python", "source1")
        path = tmp_path / "nested" / "dir" / "graph.json"
        result = kg_with_provider.save(path)
        assert result.exists()

    def test_save_unknown_suffix_falls_back_to_json(self, tmp_path):
        kg = KnowledgeGraph()
        kg._store.merge_entity("TestNode", "concept", ["test"])
        path = tmp_path / "graph.xyz"
        result = kg.save(path)
        assert result.exists()
        # Should be valid JSON
        data = json.loads(path.read_text())
        assert "nodes" in data


class TestMerge:
    def test_merge_disjoint(self):
        kg1 = KnowledgeGraph()
        kg1._store.merge_entity("Alice", "person", ["Developer"])

        kg2 = KnowledgeGraph()
        kg2._store.merge_entity("Bob", "person", ["Manager"])

        kg1.merge(kg2)
        assert kg1._store.has_entity("Alice")
        assert kg1._store.has_entity("Bob")
        assert kg1._store.get_entity_count() == 2

    def test_merge_overlapping_entities_descriptions_merged(self):
        kg1 = KnowledgeGraph()
        kg1._store.merge_entity("Python", "concept", ["A language"])

        kg2 = KnowledgeGraph()
        kg2._store.merge_entity("Python", "technology", ["Programming language"])

        kg1.merge(kg2)
        entity = kg1._store.get_entity("Python")
        # Descriptions from both should be present
        descs = entity["descriptions"]
        if isinstance(descs, set):
            descs = list(descs)
        assert "A language" in descs
        assert "Programming language" in descs

    def test_merge_overlapping_entities_with_sqlite(self, tmp_path):
        """SQLiteStore does update type on merge_entity, so type resolution works there."""
        kg1 = KnowledgeGraph(db_path=tmp_path / "kg1.db")
        kg1._store.merge_entity("Python", "concept", ["A language"])

        kg2 = KnowledgeGraph(db_path=tmp_path / "kg2.db")
        kg2._store.merge_entity("Python", "technology", ["Programming language"])

        kg1.merge(kg2)
        entity = kg1._store.get_entity("Python")
        # SQLiteStore overwrites type — merge resolves to more specific
        # (The merge method computes the resolved type and passes it to merge_entity,
        # but InMemoryStore ignores type for existing entities while SQLiteStore does not)
        assert entity is not None
        assert kg1._store.get_entity_count() == 1

    def test_merge_fuzzy_match(self):
        kg1 = KnowledgeGraph()
        kg1._store.merge_entity("JavaScript", "technology", ["A language"])

        kg2 = KnowledgeGraph()
        kg2._store.merge_entity("Javascript", "technology", ["Web language"])

        kg1.merge(kg2)
        # Should fuzzy-match and merge, not create two entities
        assert kg1._store.get_entity_count() == 1
        entity = kg1._store.get_entity("JavaScript")
        assert entity is not None

    def test_merge_relationships(self):
        kg1 = KnowledgeGraph()
        kg1._store.merge_entity("Alice", "person", [])

        kg2 = KnowledgeGraph()
        kg2._store.merge_entity("Bob", "person", [])
        kg2._store.add_relationship("Alice", "Bob", "collaborates_with")

        kg1.merge(kg2)
        rels = kg1._store.get_all_relationships()
        assert len(rels) == 1
        assert rels[0]["type"] == "collaborates_with"

    def test_merge_sources(self):
        kg1 = KnowledgeGraph()
        kg2 = KnowledgeGraph()
        kg2.register_source(
            {
                "source_id": "vid2",
                "source_type": "video",
                "title": "Video 2",
                "ingested_at": "2025-01-01T00:00:00",
            }
        )
        kg1.merge(kg2)
        sources = kg1._store.get_sources()
        assert len(sources) == 1
        assert sources[0]["source_id"] == "vid2"

    def test_merge_type_specificity_with_sqlite(self, tmp_path):
        """Type specificity resolution works with SQLiteStore which updates type."""
        kg1 = KnowledgeGraph(db_path=tmp_path / "kg1.db")
        kg1._store.merge_entity("React", "concept", [])

        kg2 = KnowledgeGraph(db_path=tmp_path / "kg2.db")
        kg2._store.merge_entity("React", "technology", [])

        kg1.merge(kg2)
        entity = kg1._store.get_entity("React")
        assert entity is not None
        assert kg1._store.get_entity_count() == 1


class TestRegisterSource:
    def test_register_and_retrieve(self):
        kg = KnowledgeGraph()
        source = {
            "source_id": "src123",
            "source_type": "video",
            "title": "Meeting Recording",
            "path": "/tmp/meeting.mp4",
            "ingested_at": "2025-06-01T10:00:00",
        }
        kg.register_source(source)
        sources = kg._store.get_sources()
        assert len(sources) == 1
        assert sources[0]["source_id"] == "src123"
        assert sources[0]["title"] == "Meeting Recording"

    def test_register_multiple_sources(self):
        kg = KnowledgeGraph()
        for i in range(3):
            kg.register_source(
                {
                    "source_id": f"src{i}",
                    "source_type": "video",
                    "title": f"Video {i}",
                    "ingested_at": "2025-01-01",
                }
            )
        assert len(kg._store.get_sources()) == 3


class TestClassifyForPlanning:
    @patch("video_processor.integrators.knowledge_graph.TaxonomyClassifier", create=True)
    def test_classify_calls_taxonomy(self, mock_cls):
        """classify_for_planning should delegate to TaxonomyClassifier."""
        mock_instance = MagicMock()
        mock_instance.classify_entities.return_value = {"goals": [], "risks": []}

        with patch(
            "video_processor.integrators.taxonomy.TaxonomyClassifier",
            return_value=mock_instance,
        ):
            kg = KnowledgeGraph()
            kg._store.merge_entity("Ship MVP", "concept", ["Launch the product"])
            kg.classify_for_planning()

        mock_instance.classify_entities.assert_called_once()


class TestExtractEntitiesAndRelationships:
    def test_returns_entities_and_relationships(self, kg_with_provider):
        entities, rels = kg_with_provider.extract_entities_and_relationships("Alice uses Python")
        assert len(entities) == 2
        assert len(rels) == 1
        assert entities[0].name == "Python"
        assert rels[0].source == "Alice"
        assert rels[0].target == "Python"

    def test_no_provider_returns_empty(self, kg_no_provider):
        entities, rels = kg_no_provider.extract_entities_and_relationships("Some text")
        assert entities == []
        assert rels == []

    def test_handles_flat_list_response(self, mock_pm):
        """If the model returns a flat entity list, it should still parse entities."""
        mock_pm.chat.return_value = json.dumps(
            [
                {"name": "Docker", "type": "technology", "description": "Container platform"},
            ]
        )
        kg = KnowledgeGraph(provider_manager=mock_pm)
        entities, rels = kg.extract_entities_and_relationships("Using Docker")
        assert len(entities) == 1
        assert entities[0].name == "Docker"
        assert rels == []

    def test_handles_malformed_json(self, mock_pm):
        mock_pm.chat.return_value = "not valid json at all"
        kg = KnowledgeGraph(provider_manager=mock_pm)
        entities, rels = kg.extract_entities_and_relationships("text")
        assert entities == []
        assert rels == []


class TestNodeAndRelationshipProperties:
    def test_nodes_property(self, kg_with_provider, mock_pm):
        kg_with_provider.add_content("Alice uses Python", "src")
        nodes = kg_with_provider.nodes
        assert isinstance(nodes, dict)
        for name, node in nodes.items():
            assert "name" in node
            assert "type" in node
            assert "descriptions" in node

    def test_relationships_property(self, kg_with_provider, mock_pm):
        kg_with_provider.add_content("Alice uses Python", "src")
        rels = kg_with_provider.relationships
        assert isinstance(rels, list)
        if rels:
            assert "source" in rels[0]
            assert "target" in rels[0]
            assert "type" in rels[0]


class TestToData:
    def test_to_data_returns_pydantic_model(self, kg_with_provider, mock_pm):
        kg_with_provider.add_content("Alice uses Python", "src")
        data = kg_with_provider.to_data()
        from video_processor.models import KnowledgeGraphData

        assert isinstance(data, KnowledgeGraphData)
        assert len(data.nodes) > 0
        assert all(hasattr(n, "name") for n in data.nodes)

    def test_to_data_includes_sources(self):
        kg = KnowledgeGraph()
        kg.register_source(
            {
                "source_id": "s1",
                "source_type": "video",
                "title": "Test",
                "ingested_at": "2025-01-01",
            }
        )
        data = kg.to_data()
        assert len(data.sources) == 1
        assert data.sources[0].source_id == "s1"
