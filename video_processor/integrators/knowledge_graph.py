"""Knowledge graph integration for organizing extracted content."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

from tqdm import tqdm

from video_processor.integrators.graph_store import GraphStore, create_store
from video_processor.models import Entity, KnowledgeGraphData, Relationship
from video_processor.providers.manager import ProviderManager
from video_processor.utils.json_parsing import parse_json_from_response

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """Integrates extracted content into a structured knowledge graph."""

    def __init__(
        self,
        provider_manager: Optional[ProviderManager] = None,
        db_path: Optional[Path] = None,
        store: Optional[GraphStore] = None,
    ):
        self.pm = provider_manager
        self._store = store or create_store(db_path)

    @property
    def nodes(self) -> Dict[str, dict]:
        """Backward-compatible read access to nodes as a dict keyed by entity name."""
        result = {}
        for entity in self._store.get_all_entities():
            name = entity["name"]
            descs = entity.get("descriptions", [])
            result[name] = {
                "id": entity.get("id", name),
                "name": name,
                "type": entity.get("type", "concept"),
                "descriptions": set(descs) if isinstance(descs, list) else descs,
                "occurrences": entity.get("occurrences", []),
            }
        return result

    @property
    def relationships(self) -> List[dict]:
        """Backward-compatible read access to relationships."""
        return self._store.get_all_relationships()

    def _chat(self, prompt: str, temperature: float = 0.3) -> str:
        """Send a chat message through ProviderManager (or return empty if none)."""
        if not self.pm:
            return ""
        return self.pm.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=temperature,
        )

    def extract_entities_and_relationships(
        self, text: str
    ) -> tuple[List[Entity], List[Relationship]]:
        """Extract entities and relationships in a single LLM call."""
        prompt = (
            "Extract all notable entities and relationships from the following content.\n\n"
            f"CONTENT:\n{text}\n\n"
            "Return a JSON object with two keys:\n"
            '- "entities": array of {"name": "...", '
            '"type": "person|concept|technology|organization|time", '
            '"description": "brief description"}\n'
            '- "relationships": array of {"source": "entity name", '
            '"target": "entity name", '
            '"type": "relationship description"}\n\n'
            "Return ONLY the JSON object."
        )
        raw = self._chat(prompt)
        parsed = parse_json_from_response(raw)

        entities = []
        rels = []

        if isinstance(parsed, dict):
            for item in parsed.get("entities", []):
                if isinstance(item, dict) and "name" in item:
                    entities.append(
                        Entity(
                            name=item["name"],
                            type=item.get("type", "concept"),
                            descriptions=[item["description"]] if item.get("description") else [],
                        )
                    )
            {e.name for e in entities}
            for item in parsed.get("relationships", []):
                if isinstance(item, dict) and "source" in item and "target" in item:
                    rels.append(
                        Relationship(
                            source=item["source"],
                            target=item["target"],
                            type=item.get("type", "related_to"),
                        )
                    )
        elif isinstance(parsed, list):
            # Fallback: if model returns a flat entity list
            for item in parsed:
                if isinstance(item, dict) and "name" in item:
                    entities.append(
                        Entity(
                            name=item["name"],
                            type=item.get("type", "concept"),
                            descriptions=[item["description"]] if item.get("description") else [],
                        )
                    )

        return entities, rels

    def add_content(self, text: str, source: str, timestamp: Optional[float] = None) -> None:
        """Add content to knowledge graph by extracting entities and relationships."""
        entities, relationships = self.extract_entities_and_relationships(text)

        snippet = text[:100] + "..." if len(text) > 100 else text

        for entity in entities:
            self._store.merge_entity(entity.name, entity.type, entity.descriptions, source=source)
            self._store.add_occurrence(entity.name, source, timestamp, snippet)

        for rel in relationships:
            if self._store.has_entity(rel.source) and self._store.has_entity(rel.target):
                self._store.add_relationship(
                    rel.source,
                    rel.target,
                    rel.type,
                    content_source=source,
                    timestamp=timestamp,
                )

    def process_transcript(self, transcript: Dict, batch_size: int = 10) -> None:
        """Process transcript segments into knowledge graph, batching for efficiency."""
        if "segments" not in transcript:
            logger.warning("Transcript missing segments")
            return

        segments = transcript["segments"]

        # Register speakers first
        for i, segment in enumerate(segments):
            speaker = segment.get("speaker", None)
            if speaker and not self._store.has_entity(speaker):
                self._store.merge_entity(speaker, "person", ["Speaker in transcript"])

        # Batch segments together for fewer API calls
        batches = []
        for start in range(0, len(segments), batch_size):
            batches.append(segments[start : start + batch_size])

        for batch in tqdm(batches, desc="Building knowledge graph", unit="batch"):
            # Combine batch text
            combined_text = " ".join(seg["text"] for seg in batch if "text" in seg)
            if not combined_text.strip():
                continue

            # Use first segment's timestamp as batch timestamp
            batch_start_idx = segments.index(batch[0])
            timestamp = batch[0].get("start", None)
            source = f"transcript_batch_{batch_start_idx}"

            self.add_content(combined_text, source, timestamp)

    def process_diagrams(self, diagrams: List[Dict]) -> None:
        """Process diagram results into knowledge graph."""
        for i, diagram in enumerate(tqdm(diagrams, desc="Processing diagrams for KG", unit="diag")):
            text_content = diagram.get("text_content", "")
            source = f"diagram_{i}"
            if text_content:
                self.add_content(text_content, source)

            diagram_id = f"diagram_{i}"
            if not self._store.has_entity(diagram_id):
                self._store.merge_entity(diagram_id, "diagram", ["Visual diagram from video"])
                self._store.add_occurrence(
                    diagram_id,
                    source if text_content else diagram_id,
                    text=f"frame_index={diagram.get('frame_index')}",
                )

    def to_data(self) -> KnowledgeGraphData:
        """Convert to pydantic KnowledgeGraphData model."""
        nodes = []
        for entity in self._store.get_all_entities():
            descs = entity.get("descriptions", [])
            if isinstance(descs, set):
                descs = list(descs)
            nodes.append(
                Entity(
                    name=entity["name"],
                    type=entity.get("type", "concept"),
                    descriptions=descs,
                    occurrences=entity.get("occurrences", []),
                )
            )

        rels = [
            Relationship(
                source=r["source"],
                target=r["target"],
                type=r.get("type", "related_to"),
                content_source=r.get("content_source"),
                timestamp=r.get("timestamp"),
            )
            for r in self._store.get_all_relationships()
        ]
        return KnowledgeGraphData(nodes=nodes, relationships=rels)

    def to_dict(self) -> Dict:
        """Convert knowledge graph to dictionary (backward-compatible)."""
        return self._store.to_dict()

    def save(self, output_path: Union[str, Path]) -> Path:
        """Save knowledge graph to JSON file."""
        output_path = Path(output_path)
        if not output_path.suffix:
            output_path = output_path.with_suffix(".json")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = self.to_data()
        output_path.write_text(data.model_dump_json(indent=2))
        logger.info(
            f"Saved knowledge graph with {self._store.get_entity_count()} nodes "
            f"and {self._store.get_relationship_count()} relationships to {output_path}"
        )
        return output_path

    @classmethod
    def from_dict(cls, data: Dict, db_path: Optional[Path] = None) -> "KnowledgeGraph":
        """Reconstruct a KnowledgeGraph from saved JSON dict."""
        kg = cls(db_path=db_path)
        for node in data.get("nodes", []):
            name = node.get("name", node.get("id", ""))
            descs = node.get("descriptions", [])
            if isinstance(descs, set):
                descs = list(descs)
            kg._store.merge_entity(
                name, node.get("type", "concept"), descs, source=node.get("source")
            )
            for occ in node.get("occurrences", []):
                kg._store.add_occurrence(
                    name,
                    occ.get("source", ""),
                    occ.get("timestamp"),
                    occ.get("text"),
                )
        for rel in data.get("relationships", []):
            kg._store.add_relationship(
                rel.get("source", ""),
                rel.get("target", ""),
                rel.get("type", "related_to"),
                content_source=rel.get("content_source"),
                timestamp=rel.get("timestamp"),
            )
        return kg

    def merge(self, other: "KnowledgeGraph") -> None:
        """Merge another KnowledgeGraph into this one."""
        for entity in other._store.get_all_entities():
            name = entity["name"]
            descs = entity.get("descriptions", [])
            if isinstance(descs, set):
                descs = list(descs)
            self._store.merge_entity(
                name, entity.get("type", "concept"), descs, source=entity.get("source")
            )
            for occ in entity.get("occurrences", []):
                self._store.add_occurrence(
                    name,
                    occ.get("source", ""),
                    occ.get("timestamp"),
                    occ.get("text"),
                )

        for rel in other._store.get_all_relationships():
            self._store.add_relationship(
                rel.get("source", ""),
                rel.get("target", ""),
                rel.get("type", "related_to"),
                content_source=rel.get("content_source"),
                timestamp=rel.get("timestamp"),
            )

    def generate_mermaid(self, max_nodes: int = 30) -> str:
        """Generate Mermaid visualization code."""
        nodes = self.nodes
        rels = self.relationships

        node_importance = {}
        for node_id in nodes:
            count = sum(1 for rel in rels if rel["source"] == node_id or rel["target"] == node_id)
            node_importance[node_id] = count

        important = sorted(node_importance.items(), key=lambda x: x[1], reverse=True)
        important_ids = [n[0] for n in important[:max_nodes]]

        mermaid = ["graph LR"]

        for nid in important_ids:
            node = nodes[nid]
            ntype = node.get("type", "concept")
            # Sanitize id for mermaid (alphanumeric + underscore only)
            safe_id = "".join(c if c.isalnum() or c == "_" else "_" for c in nid)
            safe_name = node["name"].replace('"', "'")
            mermaid.append(f'    {safe_id}["{safe_name}"]:::{ntype}')

        added = set()
        for rel in rels:
            src, tgt = rel["source"], rel["target"]
            if src in important_ids and tgt in important_ids:
                rtype = rel.get("type", "related_to")
                key = f"{src}|{tgt}|{rtype}"
                if key not in added:
                    safe_src = "".join(c if c.isalnum() or c == "_" else "_" for c in src)
                    safe_tgt = "".join(c if c.isalnum() or c == "_" else "_" for c in tgt)
                    mermaid.append(f'    {safe_src} -- "{rtype}" --> {safe_tgt}')
                    added.add(key)

        mermaid.append("    classDef person fill:#f9d5e5,stroke:#333,stroke-width:1px")
        mermaid.append("    classDef concept fill:#eeeeee,stroke:#333,stroke-width:1px")
        mermaid.append("    classDef diagram fill:#d5f9e5,stroke:#333,stroke-width:1px")
        mermaid.append("    classDef time fill:#e5d5f9,stroke:#333,stroke-width:1px")

        return "\n".join(mermaid)
