"""Auto-detect knowledge graph files in the filesystem."""

import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Common output subdirectories where graphs may live
_OUTPUT_SUBDIRS = ["results", "output", "knowledge-base"]

# Filenames we look for, in preference order
_DB_FILENAMES = ["knowledge_graph.db"]
_JSON_FILENAMES = ["knowledge_graph.json"]


def find_knowledge_graphs(
    start_dir: Optional[Path] = None,
    walk_up: bool = True,
    max_depth_down: int = 4,
) -> List[Path]:
    """Find knowledge graph files near *start_dir*, sorted by proximity.

    Search order:
    1. start_dir itself
    2. Common output subdirs (results/, output/, knowledge-base/)
    3. Recursive walk downward (up to *max_depth_down* levels)
    4. Walk upward through parent directories (if *walk_up* is True)

    Returns .db files first, then .json, each group sorted closest-first.
    """
    start_dir = Path(start_dir or Path.cwd()).resolve()
    found_db: List[tuple] = []  # (distance, path)
    found_json: List[tuple] = []
    seen: set = set()

    def _record(path: Path, distance: int) -> None:
        rp = path.resolve()
        if rp in seen or not rp.is_file():
            return
        seen.add(rp)
        bucket = found_db if rp.suffix == ".db" else found_json
        bucket.append((distance, rp))

    # 1. Direct check in start_dir
    for name in _DB_FILENAMES + _JSON_FILENAMES:
        _record(start_dir / name, 0)

    # 2. Common output subdirs
    for subdir in _OUTPUT_SUBDIRS:
        for name in _DB_FILENAMES + _JSON_FILENAMES:
            _record(start_dir / subdir / name, 1)

    # 3. Walk downward
    def _walk_down(directory: Path, depth: int) -> None:
        if depth > max_depth_down:
            return
        try:
            for child in sorted(directory.iterdir()):
                if child.is_file() and child.name in (_DB_FILENAMES + _JSON_FILENAMES):
                    _record(child, depth)
                elif child.is_dir() and not child.name.startswith("."):
                    _walk_down(child, depth + 1)
        except PermissionError:
            pass

    _walk_down(start_dir, 1)

    # 4. Walk upward
    if walk_up:
        parent = start_dir.parent
        distance = 1
        while parent != parent.parent:
            for name in _DB_FILENAMES + _JSON_FILENAMES:
                _record(parent / name, distance)
            for subdir in _OUTPUT_SUBDIRS:
                for name in _DB_FILENAMES + _JSON_FILENAMES:
                    _record(parent / subdir / name, distance + 1)
            parent = parent.parent
            distance += 1

    # Sort each group by distance, then combine db-first
    found_db.sort(key=lambda x: x[0])
    found_json.sort(key=lambda x: x[0])
    return [p for _, p in found_db] + [p for _, p in found_json]


def find_nearest_graph(start_dir: Optional[Path] = None) -> Optional[Path]:
    """Return the closest knowledge graph file, or None."""
    graphs = find_knowledge_graphs(start_dir)
    return graphs[0] if graphs else None


def describe_graph(db_path: Path) -> Dict:
    """Return summary stats for a knowledge graph file.

    Returns dict with: entity_count, relationship_count, entity_types, store_type.
    """
    from video_processor.integrators.graph_store import (
        FalkorDBStore,
        InMemoryStore,
        create_store,
    )

    db_path = Path(db_path)

    if db_path.suffix == ".json":
        import json

        data = json.loads(db_path.read_text())
        store = InMemoryStore()
        for node in data.get("nodes", []):
            store.merge_entity(
                node.get("name", ""),
                node.get("type", "concept"),
                node.get("descriptions", []),
            )
        for rel in data.get("relationships", []):
            store.add_relationship(
                rel.get("source", ""),
                rel.get("target", ""),
                rel.get("type", "related_to"),
            )
        store_type = "json"
    else:
        store = create_store(db_path)
        store_type = "falkordb" if isinstance(store, FalkorDBStore) else "inmemory"

    entities = store.get_all_entities()
    entity_types = {}
    for e in entities:
        t = e.get("type", "concept")
        entity_types[t] = entity_types.get(t, 0) + 1

    return {
        "entity_count": store.get_entity_count(),
        "relationship_count": store.get_relationship_count(),
        "entity_types": entity_types,
        "store_type": store_type,
    }
