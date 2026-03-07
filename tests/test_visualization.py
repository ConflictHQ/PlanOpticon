"""Tests for video_processor.utils.visualization module."""

import pytest

nx = pytest.importorskip("networkx", reason="networkx not installed")

from video_processor.utils.visualization import (  # noqa: E402
    compute_graph_stats,
    filter_graph,
    generate_mermaid,
    graph_to_d3_json,
    graph_to_dot,
    graph_to_networkx,
)


@pytest.fixture
def sample_kg_data():
    """Mock knowledge graph data matching to_dict() format."""
    return {
        "nodes": [
            {
                "id": "Alice",
                "name": "Alice",
                "type": "person",
                "descriptions": ["Project lead"],
                "occurrences": [{"source": "transcript_batch_0", "timestamp": 0.0}],
            },
            {
                "id": "Bob",
                "name": "Bob",
                "type": "person",
                "descriptions": ["Developer"],
                "occurrences": [],
            },
            {
                "id": "Python",
                "name": "Python",
                "type": "technology",
                "descriptions": ["Programming language"],
                "occurrences": [],
            },
            {
                "id": "Acme Corp",
                "name": "Acme Corp",
                "type": "organization",
                "descriptions": ["The company"],
                "occurrences": [],
            },
            {
                "id": "Microservices",
                "name": "Microservices",
                "type": "concept",
                "descriptions": ["Architecture pattern"],
                "occurrences": [],
            },
        ],
        "relationships": [
            {
                "source": "Alice",
                "target": "Python",
                "type": "uses",
                "content_source": "transcript_batch_0",
                "timestamp": 1.5,
            },
            {
                "source": "Bob",
                "target": "Python",
                "type": "uses",
                "content_source": "transcript_batch_0",
                "timestamp": 2.0,
            },
            {
                "source": "Alice",
                "target": "Bob",
                "type": "works_with",
                "content_source": "transcript_batch_0",
                "timestamp": 3.0,
            },
            {
                "source": "Alice",
                "target": "Acme Corp",
                "type": "employed_by",
                "content_source": "transcript_batch_1",
                "timestamp": 10.0,
            },
            {
                "source": "Acme Corp",
                "target": "Microservices",
                "type": "adopts",
                "content_source": "transcript_batch_1",
                "timestamp": 12.0,
            },
        ],
    }


@pytest.fixture
def sample_graph(sample_kg_data):
    """Pre-built NetworkX graph from sample data."""
    return graph_to_networkx(sample_kg_data)


class TestGraphToNetworkx:
    def test_node_count(self, sample_graph):
        assert sample_graph.number_of_nodes() == 5

    def test_edge_count(self, sample_graph):
        assert sample_graph.number_of_edges() == 5

    def test_node_attributes(self, sample_graph):
        alice = sample_graph.nodes["Alice"]
        assert alice["type"] == "person"
        assert alice["descriptions"] == ["Project lead"]

    def test_edge_attributes(self, sample_graph):
        edge = sample_graph.edges["Alice", "Python"]
        assert edge["type"] == "uses"
        assert edge["content_source"] == "transcript_batch_0"
        assert edge["timestamp"] == 1.5

    def test_empty_data(self):
        G = graph_to_networkx({})
        assert G.number_of_nodes() == 0
        assert G.number_of_edges() == 0

    def test_nodes_only(self):
        data = {"nodes": [{"name": "X", "type": "concept"}]}
        G = graph_to_networkx(data)
        assert G.number_of_nodes() == 1
        assert G.number_of_edges() == 0

    def test_skips_empty_names(self):
        data = {"nodes": [{"name": "", "type": "concept"}, {"name": "A"}]}
        G = graph_to_networkx(data)
        assert G.number_of_nodes() == 1

    def test_skips_empty_relationship_endpoints(self):
        data = {
            "nodes": [{"name": "A"}],
            "relationships": [{"source": "", "target": "A", "type": "x"}],
        }
        G = graph_to_networkx(data)
        assert G.number_of_edges() == 0


class TestComputeGraphStats:
    def test_basic_counts(self, sample_graph):
        stats = compute_graph_stats(sample_graph)
        assert stats["node_count"] == 5
        assert stats["edge_count"] == 5

    def test_density_range(self, sample_graph):
        stats = compute_graph_stats(sample_graph)
        assert 0.0 <= stats["density"] <= 1.0

    def test_connected_components(self, sample_graph):
        stats = compute_graph_stats(sample_graph)
        assert stats["connected_components"] == 1

    def test_type_breakdown(self, sample_graph):
        stats = compute_graph_stats(sample_graph)
        assert stats["type_breakdown"]["person"] == 2
        assert stats["type_breakdown"]["technology"] == 1
        assert stats["type_breakdown"]["organization"] == 1
        assert stats["type_breakdown"]["concept"] == 1

    def test_top_entities(self, sample_graph):
        stats = compute_graph_stats(sample_graph)
        top = stats["top_entities"]
        assert len(top) <= 10
        # Alice has degree 4 (3 out + 0 in? No: 3 out-edges, 0 in-edges = degree 3 undirected...
        # Actually in DiGraph, degree = in + out. Alice: out=3 (Python, Bob, Acme), in=0 => 3
        # Python: in=2, out=0 => 2
        assert top[0]["name"] == "Alice"

    def test_empty_graph(self):
        import networkx as nx

        G = nx.DiGraph()
        stats = compute_graph_stats(G)
        assert stats["node_count"] == 0
        assert stats["connected_components"] == 0
        assert stats["top_entities"] == []


class TestFilterGraph:
    def test_filter_by_type(self, sample_graph):
        filtered = filter_graph(sample_graph, entity_types=["person"])
        assert filtered.number_of_nodes() == 2
        for _, data in filtered.nodes(data=True):
            assert data["type"] == "person"

    def test_filter_by_min_degree(self, sample_graph):
        # Alice has degree 3 (3 out-edges), Python has degree 2 (2 in-edges)
        filtered = filter_graph(sample_graph, min_degree=3)
        assert "Alice" in filtered.nodes
        assert filtered.number_of_nodes() >= 1

    def test_filter_combined(self, sample_graph):
        filtered = filter_graph(sample_graph, entity_types=["person"], min_degree=1)
        assert all(filtered.nodes[n]["type"] == "person" for n in filtered.nodes)

    def test_filter_no_criteria(self, sample_graph):
        filtered = filter_graph(sample_graph)
        assert filtered.number_of_nodes() == sample_graph.number_of_nodes()

    def test_filter_nonexistent_type(self, sample_graph):
        filtered = filter_graph(sample_graph, entity_types=["alien"])
        assert filtered.number_of_nodes() == 0

    def test_filter_preserves_edges(self, sample_graph):
        filtered = filter_graph(sample_graph, entity_types=["person"])
        # Alice -> Bob edge should be preserved
        assert filtered.has_edge("Alice", "Bob")

    def test_filter_returns_copy(self, sample_graph):
        filtered = filter_graph(sample_graph, entity_types=["person"])
        # Modifying filtered should not affect original
        filtered.add_node("NewNode")
        assert "NewNode" not in sample_graph


class TestGenerateMermaid:
    def test_output_starts_with_graph(self, sample_graph):
        mermaid = generate_mermaid(sample_graph)
        assert mermaid.startswith("graph LR")

    def test_custom_layout(self, sample_graph):
        mermaid = generate_mermaid(sample_graph, layout="TD")
        assert mermaid.startswith("graph TD")

    def test_contains_nodes(self, sample_graph):
        mermaid = generate_mermaid(sample_graph)
        assert "Alice" in mermaid
        assert "Python" in mermaid

    def test_contains_edges(self, sample_graph):
        mermaid = generate_mermaid(sample_graph)
        assert "uses" in mermaid

    def test_contains_class_defs(self, sample_graph):
        mermaid = generate_mermaid(sample_graph)
        assert "classDef person" in mermaid
        assert "classDef concept" in mermaid

    def test_max_nodes_limit(self, sample_graph):
        mermaid = generate_mermaid(sample_graph, max_nodes=2)
        # Should only have top-2 nodes by degree
        lines = [ln for ln in mermaid.split("\n") if '["' in ln]
        assert len(lines) <= 2

    def test_empty_graph(self):
        import networkx as nx

        G = nx.DiGraph()
        mermaid = generate_mermaid(G)
        assert "graph LR" in mermaid

    def test_sanitizes_special_chars(self):
        import networkx as nx

        G = nx.DiGraph()
        G.add_node("foo bar/baz", type="concept")
        mermaid = generate_mermaid(G)
        # Node ID should be sanitized but label preserved
        assert "foo_bar_baz" in mermaid
        assert "foo bar/baz" in mermaid


class TestGraphToD3Json:
    def test_structure(self, sample_graph):
        d3 = graph_to_d3_json(sample_graph)
        assert "nodes" in d3
        assert "links" in d3

    def test_node_format(self, sample_graph):
        d3 = graph_to_d3_json(sample_graph)
        node_ids = {n["id"] for n in d3["nodes"]}
        assert "Alice" in node_ids
        alice = next(n for n in d3["nodes"] if n["id"] == "Alice")
        assert alice["group"] == "person"

    def test_link_format(self, sample_graph):
        d3 = graph_to_d3_json(sample_graph)
        assert len(d3["links"]) == 5
        link = d3["links"][0]
        assert "source" in link
        assert "target" in link
        assert "type" in link

    def test_empty_graph(self):
        import networkx as nx

        G = nx.DiGraph()
        d3 = graph_to_d3_json(G)
        assert d3 == {"nodes": [], "links": []}


class TestGraphToDot:
    def test_starts_with_digraph(self, sample_graph):
        dot = graph_to_dot(sample_graph)
        assert dot.startswith("digraph KnowledgeGraph {")

    def test_ends_with_closing_brace(self, sample_graph):
        dot = graph_to_dot(sample_graph)
        assert dot.strip().endswith("}")

    def test_contains_nodes(self, sample_graph):
        dot = graph_to_dot(sample_graph)
        assert '"Alice"' in dot
        assert '"Python"' in dot

    def test_contains_edges(self, sample_graph):
        dot = graph_to_dot(sample_graph)
        assert '"Alice" -> "Python"' in dot

    def test_edge_labels(self, sample_graph):
        dot = graph_to_dot(sample_graph)
        assert 'label="uses"' in dot

    def test_node_colors(self, sample_graph):
        dot = graph_to_dot(sample_graph)
        assert 'fillcolor="#f9d5e5"' in dot  # person color for Alice

    def test_empty_graph(self):
        import networkx as nx

        G = nx.DiGraph()
        dot = graph_to_dot(G)
        assert "digraph" in dot

    def test_special_chars_escaped(self):
        import networkx as nx

        G = nx.DiGraph()
        G.add_node('He said "hello"', type="person")
        dot = graph_to_dot(G)
        assert 'He said \\"hello\\"' in dot
