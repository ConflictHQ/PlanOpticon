"""Graph storage backends for PlanOpticon knowledge graphs."""

import json
import logging
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class GraphStore(ABC):
    """Abstract interface for knowledge graph storage backends."""

    @abstractmethod
    def merge_entity(
        self,
        name: str,
        entity_type: str,
        descriptions: List[str],
        source: Optional[str] = None,
    ) -> None:
        """Upsert an entity by case-insensitive name."""
        ...

    @abstractmethod
    def add_occurrence(
        self,
        entity_name: str,
        source: str,
        timestamp: Optional[float] = None,
        text: Optional[str] = None,
    ) -> None:
        """Add an occurrence record to an existing entity."""
        ...

    @abstractmethod
    def add_relationship(
        self,
        source: str,
        target: str,
        rel_type: str,
        content_source: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        """Add a relationship between two entities (both must already exist)."""
        ...

    @abstractmethod
    def get_entity(self, name: str) -> Optional[Dict[str, Any]]:
        """Get an entity by case-insensitive name, or None."""
        ...

    @abstractmethod
    def get_all_entities(self) -> List[Dict[str, Any]]:
        """Return all entities as dicts."""
        ...

    @abstractmethod
    def get_all_relationships(self) -> List[Dict[str, Any]]:
        """Return all relationships as dicts."""
        ...

    @abstractmethod
    def get_entity_count(self) -> int: ...

    @abstractmethod
    def get_relationship_count(self) -> int: ...

    @abstractmethod
    def has_entity(self, name: str) -> bool:
        """Check if an entity exists (case-insensitive)."""
        ...

    @abstractmethod
    def add_typed_relationship(
        self,
        source: str,
        target: str,
        edge_label: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a relationship with a custom edge label (e.g. DEPENDS_ON, USES_SYSTEM).

        Unlike add_relationship which always uses RELATED_TO, this creates edges
        with the specified label for richer graph semantics.
        """
        ...

    @abstractmethod
    def set_entity_properties(
        self,
        name: str,
        properties: Dict[str, Any],
    ) -> bool:
        """Set arbitrary key/value properties on an existing entity.

        Returns True if the entity was found and updated, False otherwise.
        """
        ...

    @abstractmethod
    def has_relationship(
        self,
        source: str,
        target: str,
        edge_label: Optional[str] = None,
    ) -> bool:
        """Check if a relationship exists between two entities.

        If edge_label is None, checks for any relationship type.
        """
        ...

    def register_source(self, source: Dict[str, Any]) -> None:
        """Register a content source. Default no-op for backends that don't support it."""
        pass

    def get_sources(self) -> List[Dict[str, Any]]:
        """Return all registered sources."""
        return []

    def get_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Get a source by ID."""
        return None

    def add_source_location(
        self,
        source_id: str,
        entity_name_lower: Optional[str] = None,
        relationship_id: Optional[int] = None,
        **kwargs,
    ) -> None:
        """Link a source to an entity or relationship with location details."""
        pass

    def get_entity_provenance(self, name: str) -> List[Dict[str, Any]]:
        """Get all source locations for an entity."""
        return []

    def raw_query(self, query_string: str) -> Any:
        """Execute a raw query against the backend (e.g. SQL for SQLite).

        Not supported by all backends — raises NotImplementedError by default.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support raw queries")

    def to_dict(self) -> Dict[str, Any]:
        """Export to JSON-compatible dict matching knowledge_graph.json format."""
        entities = self.get_all_entities()
        nodes = []
        for e in entities:
            descs = e.get("descriptions", [])
            if isinstance(descs, set):
                descs = list(descs)
            nodes.append(
                {
                    "id": e.get("id", e["name"]),
                    "name": e["name"],
                    "type": e.get("type", "concept"),
                    "descriptions": descs,
                    "occurrences": e.get("occurrences", []),
                }
            )
        result = {"nodes": nodes, "relationships": self.get_all_relationships()}
        sources = self.get_sources()
        if sources:
            result["sources"] = sources
        return result


class InMemoryStore(GraphStore):
    """In-memory graph store using Python dicts. Default fallback."""

    def __init__(self) -> None:
        self._nodes: Dict[str, Dict[str, Any]] = {}  # keyed by name.lower()
        self._relationships: List[Dict[str, Any]] = []
        self._sources: Dict[str, Dict[str, Any]] = {}  # keyed by source_id
        self._source_locations: List[Dict[str, Any]] = []

    def merge_entity(
        self,
        name: str,
        entity_type: str,
        descriptions: List[str],
        source: Optional[str] = None,
    ) -> None:
        key = name.lower()
        if key in self._nodes:
            if descriptions:
                self._nodes[key]["descriptions"].update(descriptions)
        else:
            self._nodes[key] = {
                "id": name,
                "name": name,
                "type": entity_type,
                "descriptions": set(descriptions),
                "occurrences": [],
                "source": source,
            }

    def add_occurrence(
        self,
        entity_name: str,
        source: str,
        timestamp: Optional[float] = None,
        text: Optional[str] = None,
    ) -> None:
        key = entity_name.lower()
        if key in self._nodes:
            self._nodes[key]["occurrences"].append(
                {"source": source, "timestamp": timestamp, "text": text}
            )

    def add_relationship(
        self,
        source: str,
        target: str,
        rel_type: str,
        content_source: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        self._relationships.append(
            {
                "source": source,
                "target": target,
                "type": rel_type,
                "content_source": content_source,
                "timestamp": timestamp,
            }
        )

    def get_entity(self, name: str) -> Optional[Dict[str, Any]]:
        return self._nodes.get(name.lower())

    def get_all_entities(self) -> List[Dict[str, Any]]:
        return list(self._nodes.values())

    def get_all_relationships(self) -> List[Dict[str, Any]]:
        return list(self._relationships)

    def get_entity_count(self) -> int:
        return len(self._nodes)

    def get_relationship_count(self) -> int:
        return len(self._relationships)

    def has_entity(self, name: str) -> bool:
        return name.lower() in self._nodes

    def add_typed_relationship(
        self,
        source: str,
        target: str,
        edge_label: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry: Dict[str, Any] = {
            "source": source,
            "target": target,
            "type": edge_label,
        }
        if properties:
            entry.update(properties)
        self._relationships.append(entry)

    def set_entity_properties(
        self,
        name: str,
        properties: Dict[str, Any],
    ) -> bool:
        key = name.lower()
        if key not in self._nodes:
            return False
        self._nodes[key].update(properties)
        return True

    def register_source(self, source: Dict[str, Any]) -> None:
        source_id = source.get("source_id", "")
        self._sources[source_id] = dict(source)

    def get_sources(self) -> List[Dict[str, Any]]:
        return list(self._sources.values())

    def get_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        return self._sources.get(source_id)

    def add_source_location(
        self,
        source_id: str,
        entity_name_lower: Optional[str] = None,
        relationship_id: Optional[int] = None,
        **kwargs,
    ) -> None:
        entry: Dict[str, Any] = {
            "source_id": source_id,
            "entity_name_lower": entity_name_lower,
            "relationship_id": relationship_id,
        }
        entry.update(kwargs)
        self._source_locations.append(entry)

    def get_entity_provenance(self, name: str) -> List[Dict[str, Any]]:
        name_lower = name.lower()
        results = []
        for loc in self._source_locations:
            if loc.get("entity_name_lower") == name_lower:
                entry = dict(loc)
                src = self._sources.get(loc.get("source_id", ""))
                if src:
                    entry["source"] = src
                results.append(entry)
        return results

    def has_relationship(
        self,
        source: str,
        target: str,
        edge_label: Optional[str] = None,
    ) -> bool:
        src_lower = source.lower()
        tgt_lower = target.lower()
        for rel in self._relationships:
            if rel["source"].lower() == src_lower and rel["target"].lower() == tgt_lower:
                if edge_label is None or rel.get("type") == edge_label:
                    return True
        return False


class SQLiteStore(GraphStore):
    """SQLite-backed graph store. Uses Python's built-in sqlite3 module."""

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS entities (
            name TEXT NOT NULL,
            name_lower TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL DEFAULT 'concept',
            descriptions TEXT NOT NULL DEFAULT '[]',
            source TEXT,
            properties TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS occurrences (
            entity_name_lower TEXT NOT NULL,
            source TEXT NOT NULL,
            timestamp REAL,
            text TEXT,
            FOREIGN KEY (entity_name_lower) REFERENCES entities(name_lower)
        );
        CREATE TABLE IF NOT EXISTS relationships (
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'related_to',
            content_source TEXT,
            timestamp REAL,
            properties TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_entities_name_lower ON entities(name_lower);
        CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
        CREATE INDEX IF NOT EXISTS idx_occurrences_entity ON occurrences(entity_name_lower);
        CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source);
        CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target);

        CREATE TABLE IF NOT EXISTS sources (
            source_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            title TEXT NOT NULL,
            path TEXT,
            url TEXT,
            mime_type TEXT,
            ingested_at TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS source_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL REFERENCES sources(source_id),
            entity_name_lower TEXT,
            relationship_id INTEGER,
            timestamp REAL,
            page INTEGER,
            section TEXT,
            line_start INTEGER,
            line_end INTEGER,
            text_snippet TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_source_locations_source ON source_locations(source_id);
        CREATE INDEX IF NOT EXISTS idx_source_locations_entity
            ON source_locations(entity_name_lower);
    """

    def __init__(self, db_path: Union[str, Path]) -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()

    def merge_entity(
        self,
        name: str,
        entity_type: str,
        descriptions: List[str],
        source: Optional[str] = None,
    ) -> None:
        name_lower = name.lower()
        row = self._conn.execute(
            "SELECT descriptions FROM entities WHERE name_lower = ?",
            (name_lower,),
        ).fetchone()

        if row:
            existing = json.loads(row[0])
            merged = list(set(existing + descriptions))
            self._conn.execute(
                "UPDATE entities SET descriptions = ? WHERE name_lower = ?",
                (json.dumps(merged), name_lower),
            )
        else:
            self._conn.execute(
                "INSERT INTO entities (name, name_lower, type, descriptions, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, name_lower, entity_type, json.dumps(descriptions), source),
            )
        self._conn.commit()

    def add_occurrence(
        self,
        entity_name: str,
        source: str,
        timestamp: Optional[float] = None,
        text: Optional[str] = None,
    ) -> None:
        name_lower = entity_name.lower()
        exists = self._conn.execute(
            "SELECT 1 FROM entities WHERE name_lower = ?", (name_lower,)
        ).fetchone()
        if not exists:
            return
        self._conn.execute(
            "INSERT INTO occurrences (entity_name_lower, source, timestamp, text) "
            "VALUES (?, ?, ?, ?)",
            (name_lower, source, timestamp, text),
        )
        self._conn.commit()

    def add_relationship(
        self,
        source: str,
        target: str,
        rel_type: str,
        content_source: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO relationships (source, target, type, content_source, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (source, target, rel_type, content_source, timestamp),
        )
        self._conn.commit()

    def get_entity(self, name: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT name, type, descriptions, source FROM entities WHERE name_lower = ?",
            (name.lower(),),
        ).fetchone()
        if not row:
            return None

        entity_name = row[0]
        occ_rows = self._conn.execute(
            "SELECT source, timestamp, text FROM occurrences WHERE entity_name_lower = ?",
            (name.lower(),),
        ).fetchall()
        occurrences = [{"source": o[0], "timestamp": o[1], "text": o[2]} for o in occ_rows]

        return {
            "id": entity_name,
            "name": entity_name,
            "type": row[1] or "concept",
            "descriptions": json.loads(row[2]) if row[2] else [],
            "occurrences": occurrences,
            "source": row[3],
        }

    def get_all_entities(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT name, name_lower, type, descriptions, source FROM entities"
        ).fetchall()
        entities = []
        for row in rows:
            name_lower = row[1]
            occ_rows = self._conn.execute(
                "SELECT source, timestamp, text FROM occurrences WHERE entity_name_lower = ?",
                (name_lower,),
            ).fetchall()
            occurrences = [{"source": o[0], "timestamp": o[1], "text": o[2]} for o in occ_rows]
            entities.append(
                {
                    "id": row[0],
                    "name": row[0],
                    "type": row[2] or "concept",
                    "descriptions": json.loads(row[3]) if row[3] else [],
                    "occurrences": occurrences,
                    "source": row[4],
                }
            )
        return entities

    def get_all_relationships(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT source, target, type, content_source, timestamp FROM relationships"
        ).fetchall()
        return [
            {
                "source": row[0],
                "target": row[1],
                "type": row[2] or "related_to",
                "content_source": row[3],
                "timestamp": row[4],
            }
            for row in rows
        ]

    def get_entity_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM entities").fetchone()
        return row[0] if row else 0

    def get_relationship_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM relationships").fetchone()
        return row[0] if row else 0

    def has_entity(self, name: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM entities WHERE name_lower = ?", (name.lower(),)
        ).fetchone()
        return row is not None

    def raw_query(self, query_string: str) -> Any:
        """Execute a raw SQL query and return all rows."""
        cursor = self._conn.execute(query_string)
        return cursor.fetchall()

    def add_typed_relationship(
        self,
        source: str,
        target: str,
        edge_label: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO relationships (source, target, type, properties) VALUES (?, ?, ?, ?)",
            (source, target, edge_label, json.dumps(properties or {})),
        )
        self._conn.commit()

    def set_entity_properties(
        self,
        name: str,
        properties: Dict[str, Any],
    ) -> bool:
        name_lower = name.lower()
        if not self.has_entity(name):
            return False
        if not properties:
            return True
        row = self._conn.execute(
            "SELECT properties FROM entities WHERE name_lower = ?", (name_lower,)
        ).fetchone()
        existing = json.loads(row[0]) if row and row[0] else {}
        existing.update(properties)
        self._conn.execute(
            "UPDATE entities SET properties = ? WHERE name_lower = ?",
            (json.dumps(existing), name_lower),
        )
        self._conn.commit()
        return True

    def has_relationship(
        self,
        source: str,
        target: str,
        edge_label: Optional[str] = None,
    ) -> bool:
        if edge_label:
            row = self._conn.execute(
                "SELECT 1 FROM relationships "
                "WHERE LOWER(source) = ? AND LOWER(target) = ? AND type = ?",
                (source.lower(), target.lower(), edge_label),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT 1 FROM relationships WHERE LOWER(source) = ? AND LOWER(target) = ?",
                (source.lower(), target.lower()),
            ).fetchone()
        return row is not None

    def register_source(self, source: Dict[str, Any]) -> None:
        source_id = source.get("source_id", "")
        existing = self._conn.execute(
            "SELECT 1 FROM sources WHERE source_id = ?", (source_id,)
        ).fetchone()
        if existing:
            self._conn.execute(
                "UPDATE sources SET source_type = ?, title = ?, path = ?, url = ?, "
                "mime_type = ?, ingested_at = ?, metadata = ? WHERE source_id = ?",
                (
                    source.get("source_type", ""),
                    source.get("title", ""),
                    source.get("path"),
                    source.get("url"),
                    source.get("mime_type"),
                    source.get("ingested_at", ""),
                    json.dumps(source.get("metadata", {})),
                    source_id,
                ),
            )
        else:
            self._conn.execute(
                "INSERT INTO sources (source_id, source_type, title, path, url, "
                "mime_type, ingested_at, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    source_id,
                    source.get("source_type", ""),
                    source.get("title", ""),
                    source.get("path"),
                    source.get("url"),
                    source.get("mime_type"),
                    source.get("ingested_at", ""),
                    json.dumps(source.get("metadata", {})),
                ),
            )
        self._conn.commit()

    def get_sources(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT source_id, source_type, title, path, url, mime_type, "
            "ingested_at, metadata FROM sources"
        ).fetchall()
        return [
            {
                "source_id": r[0],
                "source_type": r[1],
                "title": r[2],
                "path": r[3],
                "url": r[4],
                "mime_type": r[5],
                "ingested_at": r[6],
                "metadata": json.loads(r[7]) if r[7] else {},
            }
            for r in rows
        ]

    def get_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT source_id, source_type, title, path, url, mime_type, "
            "ingested_at, metadata FROM sources WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "source_id": row[0],
            "source_type": row[1],
            "title": row[2],
            "path": row[3],
            "url": row[4],
            "mime_type": row[5],
            "ingested_at": row[6],
            "metadata": json.loads(row[7]) if row[7] else {},
        }

    def add_source_location(
        self,
        source_id: str,
        entity_name_lower: Optional[str] = None,
        relationship_id: Optional[int] = None,
        **kwargs,
    ) -> None:
        self._conn.execute(
            "INSERT INTO source_locations (source_id, entity_name_lower, relationship_id, "
            "timestamp, page, section, line_start, line_end, text_snippet) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source_id,
                entity_name_lower,
                relationship_id,
                kwargs.get("timestamp"),
                kwargs.get("page"),
                kwargs.get("section"),
                kwargs.get("line_start"),
                kwargs.get("line_end"),
                kwargs.get("text_snippet"),
            ),
        )
        self._conn.commit()

    def get_entity_provenance(self, name: str) -> List[Dict[str, Any]]:
        name_lower = name.lower()
        rows = self._conn.execute(
            "SELECT sl.source_id, sl.entity_name_lower, sl.relationship_id, "
            "sl.timestamp, sl.page, sl.section, sl.line_start, sl.line_end, "
            "sl.text_snippet, s.source_type, s.title, s.path, s.url, s.mime_type, "
            "s.ingested_at, s.metadata "
            "FROM source_locations sl "
            "JOIN sources s ON sl.source_id = s.source_id "
            "WHERE sl.entity_name_lower = ?",
            (name_lower,),
        ).fetchall()
        results = []
        for r in rows:
            results.append(
                {
                    "source_id": r[0],
                    "entity_name_lower": r[1],
                    "relationship_id": r[2],
                    "timestamp": r[3],
                    "page": r[4],
                    "section": r[5],
                    "line_start": r[6],
                    "line_end": r[7],
                    "text_snippet": r[8],
                    "source": {
                        "source_id": r[0],
                        "source_type": r[9],
                        "title": r[10],
                        "path": r[11],
                        "url": r[12],
                        "mime_type": r[13],
                        "ingested_at": r[14],
                        "metadata": json.loads(r[15]) if r[15] else {},
                    },
                }
            )
        return results

    def close(self) -> None:
        """Close the SQLite connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


def create_store(db_path: Optional[Union[str, Path]] = None) -> GraphStore:
    """Create the best available graph store.

    If db_path is provided, uses SQLiteStore for persistent storage.
    Otherwise returns an InMemoryStore.
    """
    if db_path is not None:
        try:
            return SQLiteStore(db_path)
        except Exception as e:
            logger.warning(f"Failed to initialize SQLite at {db_path}: {e}. Using in-memory store.")
    return InMemoryStore()
