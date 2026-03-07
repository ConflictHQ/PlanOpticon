"""PlanOpticonExchange -- canonical interchange format.

Every command produces it, every export adapter consumes it.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from video_processor.models import Entity, Relationship, SourceRecord


class ArtifactMeta(BaseModel):
    """Pydantic mirror of the Artifact dataclass for serialisation."""

    name: str = Field(description="Artifact name")
    content: str = Field(description="Generated content (markdown, json, etc.)")
    artifact_type: str = Field(
        description="Artifact kind: project_plan, prd, roadmap, task_list, document, issues"
    )
    format: str = Field(
        default="markdown",
        description="Content format: markdown, json, mermaid",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key-value metadata",
    )


class ProjectMeta(BaseModel):
    """Lightweight project descriptor embedded in an exchange payload."""

    name: str = Field(description="Project name")
    description: str = Field(
        default="",
        description="Short project description",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO-8601 creation timestamp",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO-8601 last-updated timestamp",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Freeform tags for categorisation",
    )


class PlanOpticonExchange(BaseModel):
    """Wire format for PlanOpticon data interchange.

    Produced by every command, consumed by every export adapter.
    """

    version: str = Field(
        default="1.0",
        description="Schema version of this exchange payload",
    )
    project: ProjectMeta = Field(
        description="Project-level metadata",
    )
    entities: List[Entity] = Field(
        default_factory=list,
        description="Knowledge-graph entities",
    )
    relationships: List[Relationship] = Field(
        default_factory=list,
        description="Knowledge-graph relationships",
    )
    artifacts: List[ArtifactMeta] = Field(
        default_factory=list,
        description="Generated artifacts (plans, PRDs, etc.)",
    )
    sources: List[SourceRecord] = Field(
        default_factory=list,
        description="Content-source provenance records",
    )

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @classmethod
    def json_schema(cls) -> Dict[str, Any]:
        """Return the JSON Schema for validation / documentation."""
        return cls.model_json_schema()

    @classmethod
    def from_knowledge_graph(
        cls,
        kg_data: Dict[str, Any],
        *,
        project_name: str = "Untitled",
        project_description: str = "",
        tags: Optional[List[str]] = None,
    ) -> "PlanOpticonExchange":
        """Build an exchange payload from a ``KnowledgeGraph.to_dict()`` dict.

        The dict is expected to have ``nodes`` and ``relationships`` keys,
        with an optional ``sources`` key.
        """
        entities = [Entity(**_normalise_entity(n)) for n in kg_data.get("nodes", [])]
        relationships = [
            Relationship(**_normalise_relationship(r)) for r in kg_data.get("relationships", [])
        ]
        sources = [SourceRecord(**s) for s in kg_data.get("sources", [])]

        now = datetime.now().isoformat()
        project = ProjectMeta(
            name=project_name,
            description=project_description,
            created_at=now,
            updated_at=now,
            tags=tags or [],
        )

        return cls(
            project=project,
            entities=entities,
            relationships=relationships,
            sources=sources,
        )

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def to_file(self, path: str | Path) -> Path:
        """Serialise this exchange to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2))
        return path

    @classmethod
    def from_file(cls, path: str | Path) -> "PlanOpticonExchange":
        """Deserialise an exchange from a JSON file."""
        path = Path(path)
        raw = json.loads(path.read_text())
        return cls.model_validate(raw)

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def merge(self, other: "PlanOpticonExchange") -> None:
        """Merge *other* into this exchange, deduplicating entities by name."""
        existing_names = {e.name for e in self.entities}
        for entity in other.entities:
            if entity.name not in existing_names:
                self.entities.append(entity)
                existing_names.add(entity.name)

        existing_rels = {(r.source, r.target, r.type) for r in self.relationships}
        for rel in other.relationships:
            key = (rel.source, rel.target, rel.type)
            if key not in existing_rels:
                self.relationships.append(rel)
                existing_rels.add(key)

        existing_artifact_names = {a.name for a in self.artifacts}
        for artifact in other.artifacts:
            if artifact.name not in existing_artifact_names:
                self.artifacts.append(artifact)
                existing_artifact_names.add(artifact.name)

        existing_source_ids = {s.source_id for s in self.sources}
        for source in other.sources:
            if source.source_id not in existing_source_ids:
                self.sources.append(source)
                existing_source_ids.add(source.source_id)

        self.project.updated_at = datetime.now().isoformat()


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _normalise_entity(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce a KG node dict into Entity-compatible kwargs."""
    return {
        "name": raw.get("name", raw.get("id", "")),
        "type": raw.get("type", "concept"),
        "descriptions": list(raw.get("descriptions", [])),
        "source": raw.get("source"),
        "occurrences": raw.get("occurrences", []),
    }


def _normalise_relationship(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce a KG relationship dict into Relationship-compatible kwargs."""
    return {
        "source": raw.get("source", ""),
        "target": raw.get("target", ""),
        "type": raw.get("type", "related_to"),
        "content_source": raw.get("content_source"),
        "timestamp": raw.get("timestamp"),
    }
