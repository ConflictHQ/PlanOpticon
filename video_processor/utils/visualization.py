"""Graph visualization and analysis utilities using NetworkX."""

from typing import Dict, List, Optional

try:
    import networkx as nx
except ImportError:
    raise ImportError(
        "networkx is required for graph visualization. Install it with: pip install networkx"
    )


def graph_to_networkx(kg_data: dict) -> "nx.DiGraph":
    """Convert knowledge graph dict (from to_dict()) to NetworkX directed graph.

    Nodes get attributes: type, descriptions, source, occurrences
    Edges get attributes: type, content_source, timestamp
    """
    G = nx.DiGraph()

    for node in kg_data.get("nodes", []):
        name = node.get("name", node.get("id", ""))
        if not name:
            continue
        G.add_node(
            name,
            type=node.get("type", "concept"),
            descriptions=node.get("descriptions", []),
            source=node.get("source"),
            occurrences=node.get("occurrences", []),
        )

    for rel in kg_data.get("relationships", []):
        src = rel.get("source", "")
        tgt = rel.get("target", "")
        if not src or not tgt:
            continue
        G.add_edge(
            src,
            tgt,
            type=rel.get("type", "related_to"),
            content_source=rel.get("content_source"),
            timestamp=rel.get("timestamp"),
        )

    return G


def compute_graph_stats(G: "nx.DiGraph") -> dict:
    """Return graph statistics.

    Keys: node_count, edge_count, density, connected_components,
    type_breakdown, top_entities (by degree, top 10).
    """
    undirected = G.to_undirected()
    components = nx.number_connected_components(undirected) if len(G) > 0 else 0

    type_breakdown: Dict[str, int] = {}
    for _, data in G.nodes(data=True):
        ntype = data.get("type", "concept")
        type_breakdown[ntype] = type_breakdown.get(ntype, 0) + 1

    degree_list = sorted(G.degree(), key=lambda x: x[1], reverse=True)
    top_entities = [{"name": name, "degree": deg} for name, deg in degree_list[:10]]

    return {
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "density": nx.density(G),
        "connected_components": components,
        "type_breakdown": type_breakdown,
        "top_entities": top_entities,
    }


def filter_graph(
    G: "nx.DiGraph",
    entity_types: Optional[List[str]] = None,
    min_degree: Optional[int] = None,
) -> "nx.DiGraph":
    """Return subgraph filtered by entity type list and/or minimum degree."""
    nodes = set(G.nodes())

    if entity_types is not None:
        types_set = set(entity_types)
        nodes = {n for n in nodes if G.nodes[n].get("type", "concept") in types_set}

    if min_degree is not None:
        nodes = {n for n in nodes if G.degree(n) >= min_degree}

    return G.subgraph(nodes).copy()


def _sanitize_id(name: str) -> str:
    """Create a Mermaid-safe identifier from a node name."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in name)


def generate_mermaid(G: "nx.DiGraph", max_nodes: int = 30, layout: str = "LR") -> str:
    """Generate Mermaid diagram from NetworkX graph.

    Selects top nodes by degree. Layout can be LR, TD, etc.
    """
    degree_sorted = sorted(G.degree(), key=lambda x: x[1], reverse=True)
    top_nodes = {name for name, _ in degree_sorted[:max_nodes]}

    lines = [f"graph {layout}"]

    for name in top_nodes:
        data = G.nodes[name]
        ntype = data.get("type", "concept")
        safe_id = _sanitize_id(name)
        safe_name = name.replace('"', "'")
        lines.append(f'    {safe_id}["{safe_name}"]:::{ntype}')

    added = set()
    for src, tgt, data in G.edges(data=True):
        if src in top_nodes and tgt in top_nodes:
            rtype = data.get("type", "related_to")
            key = (src, tgt, rtype)
            if key not in added:
                lines.append(f'    {_sanitize_id(src)} -- "{rtype}" --> {_sanitize_id(tgt)}')
                added.add(key)

    lines.append("    classDef person fill:#f9d5e5,stroke:#333,stroke-width:1px")
    lines.append("    classDef concept fill:#eeeeee,stroke:#333,stroke-width:1px")
    lines.append("    classDef technology fill:#d5e5f9,stroke:#333,stroke-width:1px")
    lines.append("    classDef organization fill:#f9f5d5,stroke:#333,stroke-width:1px")
    lines.append("    classDef diagram fill:#d5f9e5,stroke:#333,stroke-width:1px")
    lines.append("    classDef time fill:#e5d5f9,stroke:#333,stroke-width:1px")

    return "\n".join(lines)


def graph_to_d3_json(G: "nx.DiGraph") -> dict:
    """Export to D3-compatible format.

    Returns {"nodes": [{"id": ..., "group": ...}], "links": [...]}.
    """
    nodes = []
    for name, data in G.nodes(data=True):
        nodes.append(
            {
                "id": name,
                "group": data.get("type", "concept"),
                "descriptions": data.get("descriptions", []),
            }
        )

    links = []
    for src, tgt, data in G.edges(data=True):
        links.append(
            {
                "source": src,
                "target": tgt,
                "type": data.get("type", "related_to"),
            }
        )

    return {"nodes": nodes, "links": links}


def graph_to_dot(G: "nx.DiGraph") -> str:
    """Export to Graphviz DOT format."""
    lines = ["digraph KnowledgeGraph {"]
    lines.append("    rankdir=LR;")
    lines.append('    node [shape=box, style="rounded,filled", fontname="Helvetica"];')
    lines.append("")

    type_colors = {
        "person": "#f9d5e5",
        "concept": "#eeeeee",
        "technology": "#d5e5f9",
        "organization": "#f9f5d5",
        "diagram": "#d5f9e5",
        "time": "#e5d5f9",
    }

    for name, data in G.nodes(data=True):
        ntype = data.get("type", "concept")
        color = type_colors.get(ntype, "#eeeeee")
        escaped = name.replace('"', '\\"')
        lines.append(f'    "{escaped}" [fillcolor="{color}", label="{escaped}"];')

    lines.append("")
    for src, tgt, data in G.edges(data=True):
        rtype = data.get("type", "related_to")
        escaped_src = src.replace('"', '\\"')
        escaped_tgt = tgt.replace('"', '\\"')
        escaped_type = rtype.replace('"', '\\"')
        lines.append(f'    "{escaped_src}" -> "{escaped_tgt}" [label="{escaped_type}"];')

    lines.append("}")
    return "\n".join(lines)
