"""Tests for graph query engine."""

import json
from unittest.mock import MagicMock

import pytest

from video_processor.integrators.graph_query import GraphQueryEngine, QueryResult
from video_processor.integrators.graph_store import InMemoryStore


def _make_populated_store():
    """Create a store with test data."""
    store = InMemoryStore()
    store.merge_entity("Python", "technology", ["A programming language"])
    store.merge_entity("Django", "technology", ["A web framework"])
    store.merge_entity("Alice", "person", ["Software engineer"])
    store.merge_entity("Bob", "person", ["Product manager"])
    store.merge_entity("Acme Corp", "organization", ["A tech company"])
    store.add_relationship("Alice", "Python", "uses")
    store.add_relationship("Alice", "Bob", "works_with")
    store.add_relationship("Django", "Python", "built_on")
    store.add_relationship("Alice", "Acme Corp", "employed_by")
    return store


class TestQueryResultToText:
    def test_text_with_dict_data(self):
        r = QueryResult(
            data={"entity_count": 5, "relationship_count": 3},
            query_type="filter",
            explanation="Stats",
        )
        text = r.to_text()
        assert "entity_count: 5" in text
        assert "relationship_count: 3" in text

    def test_text_with_list_of_entities(self):
        r = QueryResult(
            data=[{"name": "Python", "type": "technology", "descriptions": ["A language"]}],
            query_type="filter",
        )
        text = r.to_text()
        assert "Python" in text
        assert "technology" in text

    def test_text_with_empty_list(self):
        r = QueryResult(data=[], query_type="filter")
        assert "No results" in r.to_text()

    def test_text_with_relationships(self):
        r = QueryResult(
            data=[{"source": "A", "target": "B", "type": "knows"}],
            query_type="filter",
        )
        text = r.to_text()
        assert "A" in text
        assert "B" in text
        assert "knows" in text


class TestQueryResultToJson:
    def test_json_roundtrip(self):
        r = QueryResult(data={"key": "val"}, query_type="filter", raw_query="test()")
        parsed = json.loads(r.to_json())
        assert parsed["query_type"] == "filter"
        assert parsed["data"]["key"] == "val"
        assert parsed["raw_query"] == "test()"


class TestQueryResultToMermaid:
    def test_mermaid_with_entities_and_rels(self):
        r = QueryResult(
            data=[
                {"name": "Alice", "type": "person"},
                {"name": "Bob", "type": "person"},
                {"source": "Alice", "target": "Bob", "type": "knows"},
            ],
            query_type="filter",
        )
        mermaid = r.to_mermaid()
        assert "graph LR" in mermaid
        assert "Alice" in mermaid
        assert "Bob" in mermaid
        assert "knows" in mermaid

    def test_mermaid_empty(self):
        r = QueryResult(data=[], query_type="filter")
        mermaid = r.to_mermaid()
        assert "graph LR" in mermaid


class TestDirectMode:
    def test_stats(self):
        store = _make_populated_store()
        engine = GraphQueryEngine(store)
        result = engine.stats()
        assert result.data["entity_count"] == 5
        assert result.data["relationship_count"] == 4
        assert result.data["entity_types"]["technology"] == 2
        assert result.data["entity_types"]["person"] == 2

    def test_entities_no_filter(self):
        store = _make_populated_store()
        engine = GraphQueryEngine(store)
        result = engine.entities()
        assert len(result.data) == 5

    def test_entities_filter_by_name(self):
        store = _make_populated_store()
        engine = GraphQueryEngine(store)
        result = engine.entities(name="python")
        assert len(result.data) == 1
        assert result.data[0]["name"] == "Python"

    def test_entities_filter_by_type(self):
        store = _make_populated_store()
        engine = GraphQueryEngine(store)
        result = engine.entities(entity_type="person")
        assert len(result.data) == 2
        names = {e["name"] for e in result.data}
        assert names == {"Alice", "Bob"}

    def test_entities_filter_by_both(self):
        store = _make_populated_store()
        engine = GraphQueryEngine(store)
        result = engine.entities(name="ali", entity_type="person")
        assert len(result.data) == 1
        assert result.data[0]["name"] == "Alice"

    def test_entities_case_insensitive(self):
        store = _make_populated_store()
        engine = GraphQueryEngine(store)
        result = engine.entities(name="PYTHON")
        assert len(result.data) == 1

    def test_relationships_no_filter(self):
        store = _make_populated_store()
        engine = GraphQueryEngine(store)
        result = engine.relationships()
        assert len(result.data) == 4

    def test_relationships_filter_by_source(self):
        store = _make_populated_store()
        engine = GraphQueryEngine(store)
        result = engine.relationships(source="alice")
        assert len(result.data) == 3

    def test_relationships_filter_by_type(self):
        store = _make_populated_store()
        engine = GraphQueryEngine(store)
        result = engine.relationships(rel_type="uses")
        assert len(result.data) == 1

    def test_neighbors(self):
        store = _make_populated_store()
        engine = GraphQueryEngine(store)
        result = engine.neighbors("Alice")
        # Alice connects to Python, Bob, Acme Corp
        entities = [item for item in result.data if "name" in item]
        rels = [item for item in result.data if "source" in item and "target" in item]
        assert len(entities) >= 2  # Alice + neighbors
        assert len(rels) >= 1

    def test_neighbors_not_found(self):
        store = _make_populated_store()
        engine = GraphQueryEngine(store)
        result = engine.neighbors("Ghost")
        assert result.data == []
        assert "not found" in result.explanation

    def test_cypher_raises_on_inmemory(self):
        store = InMemoryStore()
        engine = GraphQueryEngine(store)
        with pytest.raises(NotImplementedError):
            engine.cypher("MATCH (n) RETURN n")

    def test_entities_limit(self):
        store = _make_populated_store()
        engine = GraphQueryEngine(store)
        result = engine.entities(limit=2)
        assert len(result.data) == 2


class TestFromJsonPath:
    def test_load_from_json(self, tmp_path):
        data = {
            "nodes": [
                {"name": "Python", "type": "technology", "descriptions": ["A language"]},
                {"name": "Alice", "type": "person", "descriptions": ["Engineer"]},
            ],
            "relationships": [
                {"source": "Alice", "target": "Python", "type": "uses"},
            ],
        }
        jf = tmp_path / "kg.json"
        jf.write_text(json.dumps(data))
        engine = GraphQueryEngine.from_json_path(jf)
        result = engine.stats()
        assert result.data["entity_count"] == 2
        assert result.data["relationship_count"] == 1


# Conditional FalkorDB tests
_falkordb_available = False
try:
    import redislite  # noqa: F401

    _falkordb_available = True
except ImportError:
    pass


@pytest.mark.skipif(not _falkordb_available, reason="falkordblite not installed")
class TestFalkorDBQuery:
    def test_cypher_passthrough(self, tmp_path):
        from video_processor.integrators.graph_store import FalkorDBStore

        store = FalkorDBStore(tmp_path / "test.db")
        store.merge_entity("Python", "technology", ["A language"])
        engine = GraphQueryEngine(store)
        result = engine.cypher("MATCH (e:Entity) RETURN e.name")
        assert len(result.data) >= 1
        assert result.query_type == "cypher"
        store.close()

    def test_raw_query_on_store(self, tmp_path):
        from video_processor.integrators.graph_store import FalkorDBStore

        store = FalkorDBStore(tmp_path / "test.db")
        store.merge_entity("Alice", "person", ["Engineer"])
        rows = store.raw_query("MATCH (e:Entity) RETURN e.name")
        assert len(rows) >= 1
        store.close()


class TestAgenticMode:
    def test_ask_requires_provider(self):
        store = _make_populated_store()
        engine = GraphQueryEngine(store, provider_manager=None)
        result = engine.ask("What technologies are used?")
        assert result.query_type == "agentic"
        assert "requires" in result.explanation.lower()

    def test_ask_with_mock_llm(self):
        store = _make_populated_store()
        mock_pm = MagicMock()
        # First call: plan generation — return entities action
        # Second call: synthesis — return a summary
        mock_pm.chat.side_effect = [
            '{"action": "entities", "entity_type": "technology"}',
            "The knowledge graph contains two technologies: Python and Django.",
        ]
        engine = GraphQueryEngine(store, provider_manager=mock_pm)
        result = engine.ask("What technologies are in the graph?")
        assert result.query_type == "agentic"
        assert mock_pm.chat.call_count == 2
        assert "Python" in result.explanation or len(result.data) >= 1

    def test_ask_with_stats_action(self):
        store = _make_populated_store()
        mock_pm = MagicMock()
        mock_pm.chat.side_effect = [
            '{"action": "stats"}',
            "The graph has 5 entities and 4 relationships.",
        ]
        engine = GraphQueryEngine(store, provider_manager=mock_pm)
        result = engine.ask("How big is this graph?")
        assert result.data["entity_count"] == 5

    def test_ask_with_neighbors_action(self):
        store = _make_populated_store()
        mock_pm = MagicMock()
        mock_pm.chat.side_effect = [
            '{"action": "neighbors", "entity_name": "Alice"}',
            "Alice is connected to Python, Bob, and Acme Corp.",
        ]
        engine = GraphQueryEngine(store, provider_manager=mock_pm)
        result = engine.ask("What is Alice connected to?")
        assert result.query_type == "agentic"
        assert len(result.data) > 0

    def test_ask_handles_unparseable_plan(self):
        store = _make_populated_store()
        mock_pm = MagicMock()
        mock_pm.chat.return_value = "I don't understand"
        engine = GraphQueryEngine(store, provider_manager=mock_pm)
        result = engine.ask("Gibberish?")
        assert result.data is None
        assert "parse" in result.explanation.lower() or "could not" in result.explanation.lower()
