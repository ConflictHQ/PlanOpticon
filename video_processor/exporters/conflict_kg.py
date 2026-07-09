"""Export knowledge graphs in the canonical conflict-kg/v1 interchange format.

One contract, two encodings: a JSON document for small/medium graphs and a
two-table SQLite database (D1-compatible) for large ones. Every Conflict tool
reads and writes this shape, so a graph from any tool loads anywhere without
per-source adapters.

Contract:
    {
      "format": "conflict-kg/v1",
      "nodes": [{"id": str, "name": str, "type": str, "props": {}}],
      "edges": [{"source": node-id, "target": node-id, "type": str, "props": {}}]
    }

Node `id` is the entity's case-insensitive name (the store's identity key);
edge `source`/`target` reference node ids so loaders are O(1).
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

FORMAT_ID = "conflict-kg/v1"

_SQLITE_SCHEMA = """
CREATE TABLE nodes (id TEXT PRIMARY KEY, name TEXT, type TEXT, props JSON);
CREATE TABLE edges (source TEXT, target TEXT, type TEXT, props JSON);
CREATE INDEX idx_edges_source ON edges(source);
CREATE INDEX idx_edges_target ON edges(target);
"""


def to_conflict_kg(kg_dict: Dict) -> Dict:
    """Project a KnowledgeGraph.to_dict() payload onto the conflict-kg/v1 shape.

    Node ids are the lowercased entity names — the store's real identity key —
    and edge endpoints are normalized the same way so they always reference
    node ids regardless of the casing stored on the relationship rows.
    """
    nodes = []
    for node in kg_dict.get("nodes", []):
        name = node.get("name", "")
        props = {}
        if node.get("descriptions"):
            props["descriptions"] = node["descriptions"]
        if node.get("occurrences"):
            props["occurrences"] = node["occurrences"]
        nodes.append(
            {
                "id": name.lower(),
                "name": name,
                "type": node.get("type", "concept"),
                "props": props,
            }
        )

    edges = []
    for rel in kg_dict.get("relationships", []):
        props = {}
        if rel.get("content_source") is not None:
            props["content_source"] = rel["content_source"]
        if rel.get("timestamp") is not None:
            props["timestamp"] = rel["timestamp"]
        edges.append(
            {
                "source": rel.get("source", "").lower(),
                "target": rel.get("target", "").lower(),
                "type": rel.get("type", "related_to"),
                "props": props,
            }
        )

    return {"format": FORMAT_ID, "nodes": nodes, "edges": edges}


def write_conflict_kg_json(kg_dict: Dict, output_path: Path) -> Path:
    """Write the canonical JSON encoding. Returns the output path."""
    output_path = Path(output_path)
    data = to_conflict_kg(kg_dict)
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info(
        f"Exported {len(data['nodes'])} nodes / {len(data['edges'])} edges "
        f"to {output_path} ({FORMAT_ID} JSON)"
    )
    return output_path


def write_conflict_kg_sqlite(kg_dict: Dict, output_path: Path) -> Path:
    """Write the canonical SQLite encoding (same field names, two tables).

    The output is a fresh database in the exact conflict-kg/v1 schema —
    suitable for committing to a consuming repo and loading into Cloudflare D1.
    """
    output_path = Path(output_path)
    if output_path.exists():
        output_path.unlink()

    data = to_conflict_kg(kg_dict)
    conn = sqlite3.connect(output_path)
    try:
        conn.executescript(_SQLITE_SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO nodes (id, name, type, props) VALUES (?, ?, ?, ?)",
            [(n["id"], n["name"], n["type"], json.dumps(n["props"])) for n in data["nodes"]],
        )
        conn.executemany(
            "INSERT INTO edges (source, target, type, props) VALUES (?, ?, ?, ?)",
            [(e["source"], e["target"], e["type"], json.dumps(e["props"])) for e in data["edges"]],
        )
        conn.commit()
    finally:
        conn.close()
    logger.info(
        f"Exported {len(data['nodes'])} nodes / {len(data['edges'])} edges "
        f"to {output_path} ({FORMAT_ID} SQLite)"
    )
    return output_path
