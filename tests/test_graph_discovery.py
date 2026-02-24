"""Tests for graph discovery (find_knowledge_graphs, describe_graph)."""

import json

from video_processor.integrators.graph_discovery import (
    describe_graph,
    find_knowledge_graphs,
    find_nearest_graph,
)


class TestFindKnowledgeGraphs:
    def test_finds_db_in_current_dir(self, tmp_path):
        db = tmp_path / "knowledge_graph.db"
        db.write_bytes(b"")  # placeholder
        graphs = find_knowledge_graphs(tmp_path, walk_up=False)
        assert db.resolve() in graphs

    def test_finds_in_results_subdir(self, tmp_path):
        results = tmp_path / "results"
        results.mkdir()
        db = results / "knowledge_graph.db"
        db.write_bytes(b"")
        graphs = find_knowledge_graphs(tmp_path, walk_up=False)
        assert db.resolve() in graphs

    def test_finds_in_output_subdir(self, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        db = output / "knowledge_graph.db"
        db.write_bytes(b"")
        graphs = find_knowledge_graphs(tmp_path, walk_up=False)
        assert db.resolve() in graphs

    def test_walks_up_parents(self, tmp_path):
        db = tmp_path / "knowledge_graph.db"
        db.write_bytes(b"")
        child = tmp_path / "sub" / "deep"
        child.mkdir(parents=True)
        graphs = find_knowledge_graphs(child, walk_up=True)
        assert db.resolve() in graphs

    def test_returns_empty_when_none_found(self, tmp_path):
        graphs = find_knowledge_graphs(tmp_path, walk_up=False)
        assert graphs == []

    def test_finds_json_fallback(self, tmp_path):
        jf = tmp_path / "knowledge_graph.json"
        jf.write_text('{"nodes":[], "relationships":[]}')
        graphs = find_knowledge_graphs(tmp_path, walk_up=False)
        assert jf.resolve() in graphs

    def test_db_before_json(self, tmp_path):
        db = tmp_path / "knowledge_graph.db"
        db.write_bytes(b"")
        jf = tmp_path / "knowledge_graph.json"
        jf.write_text('{"nodes":[], "relationships":[]}')
        graphs = find_knowledge_graphs(tmp_path, walk_up=False)
        assert graphs.index(db.resolve()) < graphs.index(jf.resolve())

    def test_closest_first_ordering(self, tmp_path):
        # Deeper file
        deep = tmp_path / "a" / "b"
        deep.mkdir(parents=True)
        deep_db = deep / "knowledge_graph.db"
        deep_db.write_bytes(b"")
        # Closer file
        close_db = tmp_path / "knowledge_graph.db"
        close_db.write_bytes(b"")
        graphs = find_knowledge_graphs(tmp_path, walk_up=False)
        assert graphs.index(close_db.resolve()) < graphs.index(deep_db.resolve())


class TestFindNearestGraph:
    def test_returns_closest(self, tmp_path):
        db = tmp_path / "knowledge_graph.db"
        db.write_bytes(b"")
        result = find_nearest_graph(tmp_path)
        assert result == db.resolve()

    def test_returns_none_when_empty(self, tmp_path):
        assert find_nearest_graph(tmp_path) is None


class TestDescribeGraph:
    def test_describe_json_graph(self, tmp_path):
        data = {
            "nodes": [
                {"name": "Python", "type": "technology", "descriptions": ["A language"]},
                {"name": "Django", "type": "technology", "descriptions": ["A framework"]},
                {"name": "Alice", "type": "person", "descriptions": ["Engineer"]},
            ],
            "relationships": [
                {"source": "Django", "target": "Python", "type": "uses"},
            ],
        }
        jf = tmp_path / "knowledge_graph.json"
        jf.write_text(json.dumps(data))
        info = describe_graph(jf)
        assert info["entity_count"] == 3
        assert info["relationship_count"] == 1
        assert info["entity_types"]["technology"] == 2
        assert info["entity_types"]["person"] == 1
        assert info["store_type"] == "json"
