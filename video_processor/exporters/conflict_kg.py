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

# Supergraph interop contract (ConflictHQ/project-brain#60, producer
# conformance #153). PlanOpticon is a producer for the BRAIN realm: extracted
# entities land in a brain as kg-entity nodes. Conformance is additive at this
# output boundary — node ids stay the store's identity key (lowercased name,
# which the brain's build-kg/enrich-kg consumers merge on), and the contract
# rides beside them: an envelope naming the version/realm/producer, a per-node
# `props.address` in the global grammar, and per-edge attestation
# (`asserted_by`, `confidence`) so every assertion carries who said it.
# Edge `type` is the one rewritten value: it is emitted in the brain's declared
# edge vocabulary (EDGE_VERBS), and `props.raw_types` keeps the extracted verbs
# unless they are exactly that type. Attestation is multi-valued: there is one
# edge per (source, target, type), and `props.sources` lists every content
# source stating it (the wiki frontmatter's `sources` convention).
CONTRACT_VERSION = "1.0"
REALM = "brain"
PRODUCER = "planopticon"
ADDRESS_KIND = "kg-entity"

# Extracted verbs -> declared edge ids, mirroring project-brain's
# template/brain-schema.json `edges` (contract 1.0): the brain's relation
# canonicalization (project-brain#57), done at emission instead of by the
# consumer. Keys are verbs PlanOpticon's extraction really emits, lowercased,
# `_` read as a space. Targets are the extraction-facing ids only; ids that
# assert record, work-graph, federation or code-realm structure (decided_in,
# depends_on, same_as, implemented_in, ...) are never targets, even when an
# extracted verb spells one. Matching is exact ("no integration" is not
# integrates_with); an unlisted verb is `other`, the schema's unclassified
# extraction relation. Each target maps to itself, so re-export is a no-op.
OTHER_EDGE = "other"
EDGE_VERBS = {
    verb: edge
    for edge, verbs in {
        "uses": ("uses", "use", "utilizes", "operates", "accesses"),
        "provides": ("provides", "provides data to", "feeds into", "feeds data to"),
        "integrates_with": (
            "integrates with",
            "integrated with",
            "integrated into",
            "integrates",
            "plugs into",
        ),
        "relates_to": (
            "relates to",
            "related to",
            "is related to",
            "associated with",
            "is associated with",
            "tied to",
            "linked to",
        ),
        "about": ("about", "pertains to"),
        "contains": (
            "contains",
            "includes",
            "include",
            "comprises",
            "contains section",
            "contains feature",
            "includes feature",
            "has feature",
            "includes item",
        ),
        "broader": ("broader", "is a type of", "is an example of"),
        OTHER_EDGE: (OTHER_EDGE,),
    }.items()
    for verb in verbs
}


def _slug(text: str) -> str:
    """Stable id fragment from free text — the brain's `slug` id convention
    (kebab-case, alnum runs joined by '-'), so `props.address` resolves to the
    same node the brain would mint for this entity."""
    out = []
    for ch in str(text).strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-") or "item"


def address_for(name: str, repo: str = "") -> str:
    """Global address for an extracted entity: `[<repo>/]kg-entity:<slug>`."""
    addr = f"{ADDRESS_KIND}:{_slug(name)}"
    return f"{repo}/{addr}" if repo else addr


def canonical_edge_type(verb: str) -> str:
    """Declared edge id an extracted verb is emitted as: its EDGE_VERBS entry,
    else `other`."""
    return EDGE_VERBS.get(" ".join(verb.lower().replace("_", " ").split()), OTHER_EDGE)


def contract_envelope(repo: str = "") -> Dict:
    """The producer declaration a brain gates on before reading anything else."""
    env = {
        "version": CONTRACT_VERSION,
        "realm": REALM,
        "producer": PRODUCER,
        "address_kind": ADDRESS_KIND,
    }
    if repo:
        env["repo"] = repo
    return env


_SQLITE_SCHEMA = """
CREATE TABLE nodes (id TEXT PRIMARY KEY, name TEXT, type TEXT, props JSON);
CREATE TABLE edges (source TEXT, target TEXT, type TEXT, props JSON);
CREATE INDEX idx_edges_source ON edges(source);
CREATE INDEX idx_edges_target ON edges(target);
"""


def to_conflict_kg(kg_dict: Dict, repo: str = "") -> Dict:
    """Project a KnowledgeGraph.to_dict() payload onto the conflict-kg/v1 shape.

    Node ids are the lowercased entity names — the store's real identity key —
    and edge endpoints are normalized the same way so they always reference
    node ids regardless of the casing stored on the relationship rows.

    Contract v1.0 conformance rides beside that: a `contract` envelope,
    `props.address` per node, and per edge a declared-vocabulary `type` (the
    extracted verbs in `props.raw_types` when rewritten), `asserted_by` +
    `confidence`, and `props.sources` — relationships repeating one (source,
    target, type) merge into one edge attested by all their content sources.
    `repo` (optional) is the federation namespace to prefix addresses with.
    """
    nodes = []
    for node in kg_dict.get("nodes", []):
        name = node.get("name", "")
        props = {"address": address_for(name, repo)}
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

    # The store appends a relationship row per transcript batch / diagram /
    # screenshot that states it, so one edge arrives as several rows. Merge on
    # the emitted (source, target, type) — the signature brain consumers dedupe
    # on — keeping the first row's scalar props and every row's verb and source.
    edges: Dict[tuple, Dict] = {}
    observed: Dict[tuple, tuple] = {}
    for rel in kg_dict.get("relationships", []):
        verb = rel.get("type") or "related_to"
        key = (
            rel.get("source", "").lower(),
            rel.get("target", "").lower(),
            canonical_edge_type(verb),
        )
        if key not in edges:
            # Attestation: every assertion names its asserter. Confidence is the
            # extractor's when it recorded one, else 1.0 (a stated relationship).
            props = {"asserted_by": PRODUCER, "confidence": float(rel.get("confidence", 1.0))}
            if rel.get("content_source") is not None:
                props["content_source"] = rel["content_source"]
            if rel.get("timestamp") is not None:
                props["timestamp"] = rel["timestamp"]
            edges[key] = {"source": key[0], "target": key[1], "type": key[2], "props": props}
            observed[key] = (set(), set())
        verbs, sources = observed[key]
        verbs.add(verb)
        if rel.get("content_source") is not None:
            sources.add(rel["content_source"])

    for key, edge in edges.items():
        verbs, sources = observed[key]
        if sources:
            edge["props"]["sources"] = sorted(sources)
        if verbs != {edge["type"]}:
            edge["props"]["raw_types"] = sorted(verbs)

    return {
        "format": FORMAT_ID,
        "contract": contract_envelope(repo),
        "nodes": nodes,
        "edges": list(edges.values()),
    }


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
