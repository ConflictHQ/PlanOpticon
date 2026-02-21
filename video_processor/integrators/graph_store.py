"""Graph storage backends for PlanOpticon knowledge graphs."""

import logging
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
        return {"nodes": nodes, "relationships": self.get_all_relationships()}


class InMemoryStore(GraphStore):
    """In-memory graph store using Python dicts. Default fallback."""

    def __init__(self) -> None:
        self._nodes: Dict[str, Dict[str, Any]] = {}  # keyed by name.lower()
        self._relationships: List[Dict[str, Any]] = []

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


class FalkorDBStore(GraphStore):
    """FalkorDB Lite-backed graph store. Requires falkordblite package."""

    def __init__(self, db_path: Union[str, Path]) -> None:
        from falkordb import FalkorDB

        self._db_path = str(db_path)
        self._db = FalkorDB(self._db_path)
        self._graph = self._db.select_graph("knowledge")
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        for query in [
            "CREATE INDEX FOR (e:Entity) ON (e.name_lower)",
            "CREATE INDEX FOR (e:Entity) ON (e.type)",
        ]:
            try:
                self._graph.query(query)
            except Exception:
                pass  # index already exists

    def merge_entity(
        self,
        name: str,
        entity_type: str,
        descriptions: List[str],
        source: Optional[str] = None,
    ) -> None:
        name_lower = name.lower()

        # Check if entity exists
        result = self._graph.query(
            "MATCH (e:Entity {name_lower: $name_lower}) RETURN e.descriptions",
            params={"name_lower": name_lower},
        )

        if result.result_set:
            # Entity exists — merge descriptions
            existing_descs = result.result_set[0][0] or []
            merged = list(set(existing_descs + descriptions))
            self._graph.query(
                "MATCH (e:Entity {name_lower: $name_lower}) SET e.descriptions = $descs",
                params={"name_lower": name_lower, "descs": merged},
            )
        else:
            # Create new entity
            self._graph.query(
                "CREATE (e:Entity {"
                "name: $name, name_lower: $name_lower, type: $type, "
                "descriptions: $descs, source: $source"
                "})",
                params={
                    "name": name,
                    "name_lower": name_lower,
                    "type": entity_type,
                    "descs": descriptions,
                    "source": source,
                },
            )

    def add_occurrence(
        self,
        entity_name: str,
        source: str,
        timestamp: Optional[float] = None,
        text: Optional[str] = None,
    ) -> None:
        name_lower = entity_name.lower()
        self._graph.query(
            "MATCH (e:Entity {name_lower: $name_lower}) "
            "CREATE (o:Occurrence {source: $source, timestamp: $timestamp, text: $text}) "
            "CREATE (e)-[:OCCURRED_IN]->(o)",
            params={
                "name_lower": name_lower,
                "source": source,
                "timestamp": timestamp,
                "text": text,
            },
        )

    def add_relationship(
        self,
        source: str,
        target: str,
        rel_type: str,
        content_source: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        self._graph.query(
            "MATCH (a:Entity {name_lower: $src_lower}) "
            "MATCH (b:Entity {name_lower: $tgt_lower}) "
            "CREATE (a)-[:RELATED_TO {"
            "rel_type: $rel_type, content_source: $content_source, timestamp: $timestamp"
            "}]->(b)",
            params={
                "src_lower": source.lower(),
                "tgt_lower": target.lower(),
                "rel_type": rel_type,
                "content_source": content_source,
                "timestamp": timestamp,
            },
        )

    def get_entity(self, name: str) -> Optional[Dict[str, Any]]:
        result = self._graph.query(
            "MATCH (e:Entity {name_lower: $name_lower}) "
            "RETURN e.name, e.type, e.descriptions, e.source",
            params={"name_lower": name.lower()},
        )
        if not result.result_set:
            return None

        row = result.result_set[0]
        entity_name = row[0]

        # Fetch occurrences
        occ_result = self._graph.query(
            "MATCH (e:Entity {name_lower: $name_lower})-[:OCCURRED_IN]->(o:Occurrence) "
            "RETURN o.source, o.timestamp, o.text",
            params={"name_lower": name.lower()},
        )
        occurrences = [
            {"source": o[0], "timestamp": o[1], "text": o[2]} for o in occ_result.result_set
        ]

        return {
            "id": entity_name,
            "name": entity_name,
            "type": row[1] or "concept",
            "descriptions": row[2] or [],
            "occurrences": occurrences,
            "source": row[3],
        }

    def get_all_entities(self) -> List[Dict[str, Any]]:
        result = self._graph.query(
            "MATCH (e:Entity) RETURN e.name, e.name_lower, e.type, e.descriptions, e.source"
        )
        entities = []
        for row in result.result_set:
            name_lower = row[1]
            # Fetch occurrences for this entity
            occ_result = self._graph.query(
                "MATCH (e:Entity {name_lower: $name_lower})-[:OCCURRED_IN]->(o:Occurrence) "
                "RETURN o.source, o.timestamp, o.text",
                params={"name_lower": name_lower},
            )
            occurrences = [
                {"source": o[0], "timestamp": o[1], "text": o[2]} for o in occ_result.result_set
            ]
            entities.append(
                {
                    "id": row[0],
                    "name": row[0],
                    "type": row[2] or "concept",
                    "descriptions": row[3] or [],
                    "occurrences": occurrences,
                    "source": row[4],
                }
            )
        return entities

    def get_all_relationships(self) -> List[Dict[str, Any]]:
        result = self._graph.query(
            "MATCH (a:Entity)-[r:RELATED_TO]->(b:Entity) "
            "RETURN a.name, b.name, r.rel_type, r.content_source, r.timestamp"
        )
        return [
            {
                "source": row[0],
                "target": row[1],
                "type": row[2] or "related_to",
                "content_source": row[3],
                "timestamp": row[4],
            }
            for row in result.result_set
        ]

    def get_entity_count(self) -> int:
        result = self._graph.query("MATCH (e:Entity) RETURN count(e)")
        return result.result_set[0][0] if result.result_set else 0

    def get_relationship_count(self) -> int:
        result = self._graph.query("MATCH ()-[r:RELATED_TO]->() RETURN count(r)")
        return result.result_set[0][0] if result.result_set else 0

    def has_entity(self, name: str) -> bool:
        result = self._graph.query(
            "MATCH (e:Entity {name_lower: $name_lower}) RETURN count(e)",
            params={"name_lower": name.lower()},
        )
        return result.result_set[0][0] > 0 if result.result_set else False

    def close(self) -> None:
        """Release references. FalkorDB Lite handles persistence automatically."""
        self._graph = None
        self._db = None


def create_store(db_path: Optional[Union[str, Path]] = None) -> GraphStore:
    """Create the best available graph store.

    If db_path is provided and falkordblite is installed, uses FalkorDBStore.
    Otherwise falls back to InMemoryStore.
    """
    if db_path is not None:
        try:
            return FalkorDBStore(db_path)
        except ImportError:
            logger.info(
                "falkordblite not installed, falling back to in-memory store. "
                "Install with: pip install planopticon[graph]"
            )
        except Exception as e:
            logger.warning(
                f"Failed to initialize FalkorDB at {db_path}: {e}. Using in-memory store."
            )
    return InMemoryStore()
