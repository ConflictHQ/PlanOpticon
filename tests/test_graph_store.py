"""Tests for graph storage backends."""

import pytest

from video_processor.integrators.graph_store import InMemoryStore, create_store


class TestInMemoryStore:
    def test_merge_entity_creates_new(self):
        store = InMemoryStore()
        store.merge_entity("Python", "technology", ["A programming language"])
        assert store.get_entity_count() == 1
        entity = store.get_entity("python")
        assert entity is not None
        assert entity["name"] == "Python"
        assert entity["type"] == "technology"
        assert "A programming language" in entity["descriptions"]

    def test_merge_entity_case_insensitive_dedup(self):
        store = InMemoryStore()
        store.merge_entity("Python", "technology", ["Language"])
        store.merge_entity("python", "technology", ["Snake-based"])
        store.merge_entity("PYTHON", "technology", ["Popular"])
        assert store.get_entity_count() == 1
        entity = store.get_entity("Python")
        assert entity is not None
        assert "Language" in entity["descriptions"]
        assert "Snake-based" in entity["descriptions"]
        assert "Popular" in entity["descriptions"]

    def test_add_occurrence(self):
        store = InMemoryStore()
        store.merge_entity("Alice", "person", ["Engineer"])
        store.add_occurrence("Alice", "transcript_0", timestamp=10.5, text="Alice said...")
        entity = store.get_entity("alice")
        assert len(entity["occurrences"]) == 1
        assert entity["occurrences"][0]["source"] == "transcript_0"
        assert entity["occurrences"][0]["timestamp"] == 10.5

    def test_add_occurrence_nonexistent_entity(self):
        store = InMemoryStore()
        store.add_occurrence("Ghost", "transcript_0")
        # Should not crash, just no-op
        assert store.get_entity_count() == 0

    def test_add_relationship(self):
        store = InMemoryStore()
        store.merge_entity("Alice", "person", [])
        store.merge_entity("Bob", "person", [])
        store.add_relationship("Alice", "Bob", "knows", content_source="t0", timestamp=5.0)
        assert store.get_relationship_count() == 1
        rels = store.get_all_relationships()
        assert rels[0]["source"] == "Alice"
        assert rels[0]["target"] == "Bob"
        assert rels[0]["type"] == "knows"

    def test_has_entity(self):
        store = InMemoryStore()
        assert not store.has_entity("Python")
        store.merge_entity("Python", "technology", [])
        assert store.has_entity("Python")
        assert store.has_entity("python")
        assert store.has_entity("PYTHON")

    def test_get_entity_not_found(self):
        store = InMemoryStore()
        assert store.get_entity("nonexistent") is None

    def test_get_all_entities(self):
        store = InMemoryStore()
        store.merge_entity("Alice", "person", ["Engineer"])
        store.merge_entity("Bob", "person", ["Manager"])
        entities = store.get_all_entities()
        assert len(entities) == 2
        names = {e["name"] for e in entities}
        assert names == {"Alice", "Bob"}

    def test_to_dict_format(self):
        store = InMemoryStore()
        store.merge_entity("Python", "technology", ["A language"])
        store.merge_entity("Django", "technology", ["A framework"])
        store.add_relationship("Django", "Python", "uses")
        store.add_occurrence("Python", "transcript_0", timestamp=1.0, text="mentioned Python")

        data = store.to_dict()
        assert "nodes" in data
        assert "relationships" in data
        assert len(data["nodes"]) == 2
        assert len(data["relationships"]) == 1

        # Descriptions should be lists (not sets)
        for node in data["nodes"]:
            assert isinstance(node["descriptions"], list)
            assert "id" in node
            assert "name" in node
            assert "type" in node

    def test_to_dict_roundtrip(self):
        """Verify to_dict produces data that can reload into a new store."""
        store = InMemoryStore()
        store.merge_entity("Alice", "person", ["Engineer"])
        store.merge_entity("Bob", "person", ["Manager"])
        store.add_relationship("Alice", "Bob", "reports_to")
        store.add_occurrence("Alice", "src", timestamp=1.0, text="hello")

        data = store.to_dict()

        # Reload into a new store
        store2 = InMemoryStore()
        for node in data["nodes"]:
            store2.merge_entity(
                node["name"], node["type"], node["descriptions"], node.get("source")
            )
            for occ in node.get("occurrences", []):
                store2.add_occurrence(
                    node["name"], occ["source"], occ.get("timestamp"), occ.get("text")
                )
        for rel in data["relationships"]:
            store2.add_relationship(
                rel["source"],
                rel["target"],
                rel["type"],
                rel.get("content_source"),
                rel.get("timestamp"),
            )

        assert store2.get_entity_count() == 2
        assert store2.get_relationship_count() == 1

    def test_empty_store(self):
        store = InMemoryStore()
        assert store.get_entity_count() == 0
        assert store.get_relationship_count() == 0
        assert store.get_all_entities() == []
        assert store.get_all_relationships() == []
        data = store.to_dict()
        assert data == {"nodes": [], "relationships": []}


class TestCreateStore:
    def test_returns_in_memory_without_path(self):
        store = create_store()
        assert isinstance(store, InMemoryStore)

    def test_returns_in_memory_with_none_path(self):
        store = create_store(db_path=None)
        assert isinstance(store, InMemoryStore)

    def test_fallback_to_in_memory_when_falkordb_unavailable(self, tmp_path):
        """When falkordblite is not installed, should fall back gracefully."""
        store = create_store(db_path=tmp_path / "test.db")
        # Will be FalkorDBStore if installed, InMemoryStore if not
        # Either way, it should work
        store.merge_entity("Test", "concept", ["test entity"])
        assert store.get_entity_count() == 1


# Conditional FalkorDB tests
_falkordb_available = False
try:
    import redislite  # noqa: F401

    _falkordb_available = True
except ImportError:
    pass


@pytest.mark.skipif(not _falkordb_available, reason="falkordblite not installed")
class TestFalkorDBStore:
    def test_create_and_query_entity(self, tmp_path):
        from video_processor.integrators.graph_store import FalkorDBStore

        store = FalkorDBStore(tmp_path / "test.db")
        store.merge_entity("Python", "technology", ["A language"])
        assert store.get_entity_count() == 1
        entity = store.get_entity("python")
        assert entity is not None
        assert entity["name"] == "Python"
        store.close()

    def test_case_insensitive_merge(self, tmp_path):
        from video_processor.integrators.graph_store import FalkorDBStore

        store = FalkorDBStore(tmp_path / "test.db")
        store.merge_entity("Python", "technology", ["Language"])
        store.merge_entity("python", "technology", ["Snake-based"])
        assert store.get_entity_count() == 1
        entity = store.get_entity("python")
        assert "Language" in entity["descriptions"]
        assert "Snake-based" in entity["descriptions"]
        store.close()

    def test_relationships(self, tmp_path):
        from video_processor.integrators.graph_store import FalkorDBStore

        store = FalkorDBStore(tmp_path / "test.db")
        store.merge_entity("Alice", "person", [])
        store.merge_entity("Bob", "person", [])
        store.add_relationship("Alice", "Bob", "knows")
        assert store.get_relationship_count() == 1
        rels = store.get_all_relationships()
        assert rels[0]["source"] == "Alice"
        assert rels[0]["target"] == "Bob"
        store.close()

    def test_occurrences(self, tmp_path):
        from video_processor.integrators.graph_store import FalkorDBStore

        store = FalkorDBStore(tmp_path / "test.db")
        store.merge_entity("Alice", "person", ["Engineer"])
        store.add_occurrence("Alice", "transcript_0", timestamp=10.5, text="Alice said...")
        entity = store.get_entity("alice")
        assert len(entity["occurrences"]) == 1
        assert entity["occurrences"][0]["source"] == "transcript_0"
        store.close()

    def test_persistence(self, tmp_path):
        from video_processor.integrators.graph_store import FalkorDBStore

        db_path = tmp_path / "persist.db"

        store1 = FalkorDBStore(db_path)
        store1.merge_entity("Python", "technology", ["A language"])
        store1.add_relationship_count = 0  # just to trigger write
        store1.close()

        store2 = FalkorDBStore(db_path)
        assert store2.get_entity_count() == 1
        entity = store2.get_entity("python")
        assert entity["name"] == "Python"
        store2.close()

    def test_to_dict_format(self, tmp_path):
        from video_processor.integrators.graph_store import FalkorDBStore

        store = FalkorDBStore(tmp_path / "test.db")
        store.merge_entity("Python", "technology", ["A language"])
        store.merge_entity("Django", "technology", ["A framework"])
        store.add_relationship("Django", "Python", "uses")

        data = store.to_dict()
        assert len(data["nodes"]) == 2
        assert len(data["relationships"]) == 1

        for node in data["nodes"]:
            assert isinstance(node["descriptions"], list)
            assert "id" in node
            assert "name" in node

        store.close()

    def test_has_entity(self, tmp_path):
        from video_processor.integrators.graph_store import FalkorDBStore

        store = FalkorDBStore(tmp_path / "test.db")
        assert not store.has_entity("Python")
        store.merge_entity("Python", "technology", [])
        assert store.has_entity("Python")
        assert store.has_entity("python")
        store.close()
