"""Knowledge graph integration for organizing extracted content."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

from tqdm import tqdm

from video_processor.models import Entity, KnowledgeGraphData, Relationship
from video_processor.providers.manager import ProviderManager
from video_processor.utils.json_parsing import parse_json_from_response

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """Integrates extracted content into a structured knowledge graph."""

    def __init__(
        self,
        provider_manager: Optional[ProviderManager] = None,
    ):
        self.pm = provider_manager
        self.nodes: Dict[str, dict] = {}
        self.relationships: List[dict] = []

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

        for entity in entities:
            eid = entity.name
            if eid in self.nodes:
                self.nodes[eid]["occurrences"].append(
                    {
                        "source": source,
                        "timestamp": timestamp,
                        "text": text[:100] + "..." if len(text) > 100 else text,
                    }
                )
                if entity.descriptions:
                    self.nodes[eid]["descriptions"].update(entity.descriptions)
            else:
                self.nodes[eid] = {
                    "id": eid,
                    "name": entity.name,
                    "type": entity.type,
                    "descriptions": set(entity.descriptions),
                    "occurrences": [
                        {
                            "source": source,
                            "timestamp": timestamp,
                            "text": text[:100] + "..." if len(text) > 100 else text,
                        }
                    ],
                }

        for rel in relationships:
            if rel.source in self.nodes and rel.target in self.nodes:
                self.relationships.append(
                    {
                        "source": rel.source,
                        "target": rel.target,
                        "type": rel.type,
                        "content_source": source,
                        "timestamp": timestamp,
                    }
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
            if speaker and speaker not in self.nodes:
                self.nodes[speaker] = {
                    "id": speaker,
                    "name": speaker,
                    "type": "person",
                    "descriptions": {"Speaker in transcript"},
                    "occurrences": [],
                }

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
            if text_content:
                source = f"diagram_{i}"
                self.add_content(text_content, source)

            diagram_id = f"diagram_{i}"
            if diagram_id not in self.nodes:
                self.nodes[diagram_id] = {
                    "id": diagram_id,
                    "name": f"Diagram {i}",
                    "type": "diagram",
                    "descriptions": {"Visual diagram from video"},
                    "occurrences": [
                        {
                            "source": source if text_content else f"diagram_{i}",
                            "frame_index": diagram.get("frame_index"),
                        }
                    ],
                }

    def to_data(self) -> KnowledgeGraphData:
        """Convert to pydantic KnowledgeGraphData model."""
        nodes = []
        for node in self.nodes.values():
            descs = node.get("descriptions", set())
            if isinstance(descs, set):
                descs = list(descs)
            nodes.append(
                Entity(
                    name=node["name"],
                    type=node.get("type", "concept"),
                    descriptions=descs,
                    occurrences=node.get("occurrences", []),
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
            for r in self.relationships
        ]
        return KnowledgeGraphData(nodes=nodes, relationships=rels)

    def to_dict(self) -> Dict:
        """Convert knowledge graph to dictionary (backward-compatible)."""
        nodes_json = []
        for node_id, node in self.nodes.items():
            node_json = node.copy()
            descs = node.get("descriptions", set())
            node_json["descriptions"] = list(descs) if isinstance(descs, set) else descs
            nodes_json.append(node_json)

        return {"nodes": nodes_json, "relationships": self.relationships}

    def save(self, output_path: Union[str, Path]) -> Path:
        """Save knowledge graph to JSON file."""
        output_path = Path(output_path)
        if not output_path.suffix:
            output_path = output_path.with_suffix(".json")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = self.to_data()
        output_path.write_text(data.model_dump_json(indent=2))
        logger.info(
            f"Saved knowledge graph with {len(self.nodes)} nodes "
            f"and {len(self.relationships)} relationships to {output_path}"
        )
        return output_path

    @classmethod
    def from_dict(cls, data: Dict) -> "KnowledgeGraph":
        """Reconstruct a KnowledgeGraph from saved JSON dict."""
        kg = cls()
        for node in data.get("nodes", []):
            nid = node.get("id", node.get("name", ""))
            descs = node.get("descriptions", [])
            kg.nodes[nid] = {
                "id": nid,
                "name": node.get("name", nid),
                "type": node.get("type", "concept"),
                "descriptions": set(descs) if isinstance(descs, list) else descs,
                "occurrences": node.get("occurrences", []),
            }
        kg.relationships = data.get("relationships", [])
        return kg

    def merge(self, other: "KnowledgeGraph") -> None:
        """Merge another KnowledgeGraph into this one."""
        for nid, node in other.nodes.items():
            nid_lower = nid.lower()
            # Find existing node by case-insensitive match
            existing_id = None
            for eid in self.nodes:
                if eid.lower() == nid_lower:
                    existing_id = eid
                    break

            if existing_id:
                existing = self.nodes[existing_id]
                existing["occurrences"].extend(node.get("occurrences", []))
                descs = node.get("descriptions", set())
                if isinstance(descs, set):
                    existing["descriptions"].update(descs)
                elif isinstance(descs, list):
                    existing["descriptions"].update(descs)
            else:
                descs = node.get("descriptions", set())
                self.nodes[nid] = {
                    "id": nid,
                    "name": node.get("name", nid),
                    "type": node.get("type", "concept"),
                    "descriptions": set(descs) if isinstance(descs, list) else descs,
                    "occurrences": list(node.get("occurrences", [])),
                }

        self.relationships.extend(other.relationships)

    def generate_mermaid(self, max_nodes: int = 30) -> str:
        """Generate Mermaid visualization code."""
        node_importance = {}
        for node_id in self.nodes:
            count = sum(
                1
                for rel in self.relationships
                if rel["source"] == node_id or rel["target"] == node_id
            )
            node_importance[node_id] = count

        important = sorted(node_importance.items(), key=lambda x: x[1], reverse=True)
        important_ids = [n[0] for n in important[:max_nodes]]

        mermaid = ["graph LR"]

        for nid in important_ids:
            node = self.nodes[nid]
            ntype = node.get("type", "concept")
            # Sanitize id for mermaid (alphanumeric + underscore only)
            safe_id = "".join(c if c.isalnum() or c == "_" else "_" for c in nid)
            safe_name = node["name"].replace('"', "'")
            mermaid.append(f'    {safe_id}["{safe_name}"]:::{ntype}')

        added = set()
        for rel in self.relationships:
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
