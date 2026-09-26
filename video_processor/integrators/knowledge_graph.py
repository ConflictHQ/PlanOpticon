"""Knowledge graph integration for organizing extracted content."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

from tqdm import tqdm

from video_processor.evidence import check_source_revision, observation
from video_processor.integrators.graph_store import GraphStore, create_store
from video_processor.models import Entity, KnowledgeGraphData, Relationship, SourceRecord
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

    def register_source(self, source: Dict) -> None:
        """Register a content source for provenance tracking."""
        self._store.register_source(source)

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
                            confidence=item.get("confidence"),
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

    def add_content(
        self,
        text: str,
        source: str,
        timestamp: Optional[float] = None,
        source_id: Optional[str] = None,
        evidence: Optional[Dict] = None,
    ) -> None:
        """Add content to knowledge graph by extracting entities and relationships."""
        evidence = self._store._prepare_evidence(evidence)
        entities, relationships = self.extract_entities_and_relationships(text)

        snippet = text[:100] + "..." if len(text) > 100 else text

        for entity in entities:
            self._store.merge_entity(entity.name, entity.type, entity.descriptions, source=source)
            self._store.add_occurrence(entity.name, source, timestamp, snippet, evidence=evidence)
            if source_id and evidence is None:
                self._store.add_source_location(
                    source_id,
                    entity_name_lower=entity.name.lower(),
                    timestamp=timestamp,
                    text_snippet=snippet,
                )

        for rel in relationships:
            if self._store.has_entity(rel.source) and self._store.has_entity(rel.target):
                self._store.add_relationship(
                    rel.source,
                    rel.target,
                    rel.type,
                    content_source=source,
                    timestamp=timestamp,
                    evidence=evidence,
                    confidence=rel.confidence,
                )

    def _observation(self, source_id, modality, locator, detector_confidence=None):
        if source_id is None:
            return None
        source = self._store.get_source(source_id)
        if source is None:
            raise ValueError(f"source {source_id!r} must be registered before extraction")
        if modality in ("diagram", "screenshot") and locator.get("frame_index") is not None:
            locator = {**locator, "frame_index_basis": "analysis_input"}
        return observation(source, modality, locator, detector_confidence)

    def process_transcript(
        self, transcript: Dict, batch_size: int = 10, source_id: Optional[str] = None
    ) -> None:
        """Extract batches with explicit source and available segment/time ranges."""
        if "segments" not in transcript:
            logger.warning("Transcript missing segments")
            return
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        segments = [
            {**segment, "start": None, "end": None}
            if segment.get("timing_basis") == "estimated"
            else segment
            for segment in transcript["segments"]
        ]
        contexts = [
            self._observation(
                source_id,
                "transcript",
                {
                    "timestamp": segment.get("start"),
                    "end_timestamp": segment.get("end"),
                    "segment_start": index,
                    "segment_end": index,
                },
            )
            for index, segment in enumerate(segments)
        ]
        batches = []
        for start in range(0, len(segments), batch_size):
            batch = segments[start : start + batch_size]
            context = self._observation(
                source_id,
                "transcript",
                {
                    "timestamp": batch[0].get("start"),
                    "end_timestamp": batch[-1].get("end"),
                    "segment_start": start,
                    "segment_end": start + len(batch) - 1,
                },
            )
            batches.append((start, batch, context))
        # Validate every locator before mutating this modality's graph.
        for index, segment in enumerate(segments):
            speaker = segment.get("speaker")
            if speaker:
                if not self._store.has_entity(speaker):
                    self._store.merge_entity(speaker, "person", ["Speaker in transcript"])
                if contexts[index] is not None:
                    self._store.add_occurrence(
                        speaker,
                        f"{source_id}/transcript_segment_{index}",
                        segment.get("start"),
                        "Speaker annotation in extraction input",
                        evidence=contexts[index],
                    )
        for start, batch, context in tqdm(batches, desc="Building knowledge graph", unit="batch"):
            combined_text = " ".join(seg["text"] for seg in batch if "text" in seg)
            if not combined_text.strip():
                continue
            source = f"transcript_batch_{start}"
            if source_id is not None:
                source = f"{source_id}/{source}"
            self.add_content(combined_text, source, batch[0].get("start"), evidence=context)

    def process_diagrams(self, diagrams: List[Dict], source_id: Optional[str] = None) -> None:
        """Retain a diagram's frame/time/image context with its extracted claims."""
        contexts = [
            self._observation(
                source_id,
                "diagram",
                {key: diagram.get(key) for key in ("timestamp", "frame_index", "image_path")},
                diagram.get("confidence"),
            )
            for diagram in diagrams
        ]
        for index, diagram in enumerate(
            tqdm(diagrams, desc="Processing diagrams for KG", unit="diag")
        ):
            label = f"diagram_{index}"
            source = f"{source_id}/{label}" if source_id is not None else label
            text = diagram.get("text_content", "")
            context = contexts[index]
            if text:
                self.add_content(text, source, diagram.get("timestamp"), evidence=context)
            diagram_id = f"diagram_{source_id}_{index}" if source_id is not None else label
            new = not self._store.has_entity(diagram_id)
            if new:
                self._store.merge_entity(diagram_id, "diagram", ["Visual diagram from video"])
            if new or context is not None:
                self._store.add_occurrence(
                    diagram_id,
                    source,
                    diagram.get("timestamp"),
                    text=f"frame_index={diagram.get('frame_index')}",
                    evidence=context,
                )

    def process_screenshots(self, screenshots: List[Dict], source_id: Optional[str] = None) -> None:
        """Retain screen capture locators and detector uncertainty independently."""
        contexts = [
            self._observation(
                source_id,
                "screenshot",
                {key: capture.get(key) for key in ("timestamp", "frame_index", "image_path")},
                capture.get("confidence"),
            )
            for capture in screenshots
        ]
        for index, capture in enumerate(screenshots):
            label = f"screenshot_{index}"
            source = f"{source_id}/{label}" if source_id is not None else label
            text = capture.get("text_content", "")
            content_type = capture.get("content_type", "screenshot")
            context = contexts[index]
            if text:
                self.add_content(text, source, capture.get("timestamp"), evidence=context)
            for entity_name in capture.get("entities", []):
                if not entity_name or len(entity_name) < 2:
                    continue
                if not self._store.has_entity(entity_name):
                    self._store.merge_entity(
                        entity_name,
                        "concept",
                        [f"Identified in {content_type} screenshot"],
                        source=source,
                    )
                self._store.add_occurrence(
                    entity_name,
                    source,
                    capture.get("timestamp"),
                    text=f"Visible in {content_type} (frame {capture.get('frame_index', '?')})",
                    evidence=context,
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
                evidence=r.get("evidence"),
                confidence=r.get("confidence"),
            )
            for r in self._store.get_all_relationships()
        ]

        sources = [SourceRecord(**s) for s in self._store.get_sources()]

        return KnowledgeGraphData(nodes=nodes, relationships=rels, sources=sources)

    def to_dict(self) -> Dict:
        """Convert knowledge graph to dictionary (backward-compatible)."""
        return self._store.to_dict()

    def save(self, output_path: Union[str, Path]) -> Path:
        """Save knowledge graph. Defaults to .db (SQLite), also supports .json."""
        output_path = Path(output_path)
        if not output_path.suffix:
            output_path = output_path.with_suffix(".db")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_path.suffix == ".json":
            data = self.to_data()
            output_path.write_text(data.model_dump_json(indent=2))
        elif output_path.suffix == ".db":
            # If the backing store is already SQLite at this path, it's already persisted.
            # Otherwise, create a new SQLite store and copy data into it.
            from video_processor.integrators.graph_store import SQLiteStore

            if not isinstance(self._store, SQLiteStore) or self._store._db_path != str(output_path):
                target = SQLiteStore(output_path)
                for source in self._store.get_sources():
                    target.register_source(source)
                for entity in self._store.get_all_entities():
                    descs = entity.get("descriptions", [])
                    if isinstance(descs, set):
                        descs = list(descs)
                    target.merge_entity(
                        entity["name"],
                        entity.get("type", "concept"),
                        descs,
                        source=entity.get("source"),
                    )
                    for occ in entity.get("occurrences", []):
                        target.add_occurrence(
                            entity["name"],
                            occ.get("source", ""),
                            occ.get("timestamp"),
                            occ.get("text"),
                            evidence=occ.get("evidence"),
                        )
                for rel in self._store.get_all_relationships():
                    target.add_relationship(
                        rel.get("source", ""),
                        rel.get("target", ""),
                        rel.get("type", "related_to"),
                        content_source=rel.get("content_source"),
                        timestamp=rel.get("timestamp"),
                        evidence=rel.get("evidence"),
                        confidence=rel.get("confidence"),
                    )
                target.close()
        else:
            # Unknown suffix — fall back to JSON
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
        for source in data.get("sources", []):
            kg._store.register_source(source)
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
                    evidence=occ.get("evidence"),
                )
        for rel in data.get("relationships", []):
            kg._store.add_relationship(
                rel.get("source", ""),
                rel.get("target", ""),
                rel.get("type", "related_to"),
                content_source=rel.get("content_source"),
                timestamp=rel.get("timestamp"),
                evidence=rel.get("evidence"),
                confidence=rel.get("confidence"),
            )
        return kg

    # Type specificity ranking for conflict resolution during merge.
    # Higher rank = more specific type wins when two entities match.
    _TYPE_SPECIFICITY = {
        "concept": 0,
        "time": 1,
        "diagram": 1,
        "organization": 2,
        "person": 3,
        "technology": 3,
    }

    @staticmethod
    def _fuzzy_match(name_a: str, name_b: str, threshold: float = 0.85) -> bool:
        """Return True if two names are similar enough to be considered the same entity."""
        from difflib import SequenceMatcher

        return SequenceMatcher(None, name_a.lower(), name_b.lower()).ratio() >= threshold

    def _more_specific_type(self, type_a: str, type_b: str) -> str:
        """Return the more specific of two entity types."""
        rank_a = self._TYPE_SPECIFICITY.get(type_a, 1)
        rank_b = self._TYPE_SPECIFICITY.get(type_b, 1)
        return type_a if rank_a >= rank_b else type_b

    def merge(self, other: "KnowledgeGraph") -> None:
        """Merge another KnowledgeGraph into this one.

        Improvements over naive merge:
        - Fuzzy name matching (SequenceMatcher >= 0.85) to unify near-duplicate entities
        - Type conflict resolution: prefer more specific types (e.g. technology > concept)
        - Provenance: merged entities get a ``merged_from`` description entry
        """
        for source in other._store.get_sources():
            check_source_revision(self._store.get_source(source["source_id"]), source)
        for source in other._store.get_sources():
            self._store.register_source(source)

        # Build a lookup of existing entity names for fuzzy matching
        existing_entities = self._store.get_all_entities()
        existing_names = {e["name"]: e for e in existing_entities}
        # Cache lowercase -> canonical name for fast lookup
        name_index: dict[str, str] = {n.lower(): n for n in existing_names}

        resolved_names = {}
        for entity in other._store.get_all_entities():
            incoming_name = entity["name"]
            descs = entity.get("descriptions", [])
            if isinstance(descs, set):
                descs = list(descs)
            incoming_type = entity.get("type", "concept")

            # Try exact match first (case-insensitive), then fuzzy
            matched_name: Optional[str] = None
            if incoming_name.lower() in name_index:
                matched_name = name_index[incoming_name.lower()]
            elif incoming_type != "diagram":
                for existing_name in existing_names:
                    if self._fuzzy_match(incoming_name, existing_name):
                        matched_name = existing_name
                        break

            if matched_name is not None:
                # Resolve type conflict
                existing_type = existing_names[matched_name].get("type", "concept")
                resolved_type = self._more_specific_type(existing_type, incoming_type)

                # Add merge provenance
                merge_note = f"merged_from:{incoming_name}"
                merged_descs = descs if incoming_name == matched_name else descs + [merge_note]

                self._store.merge_entity(
                    matched_name, resolved_type, merged_descs, source=entity.get("source")
                )
                target_name = matched_name
            else:
                self._store.merge_entity(
                    incoming_name, incoming_type, descs, source=entity.get("source")
                )
                # Update indexes for subsequent fuzzy matches within this merge
                existing_names[incoming_name] = entity
                name_index[incoming_name.lower()] = incoming_name
                target_name = incoming_name

            resolved_names[incoming_name.lower()] = target_name
            for occ in entity.get("occurrences", []):
                self._store.add_occurrence(
                    target_name,
                    occ.get("source", ""),
                    occ.get("timestamp"),
                    occ.get("text"),
                    evidence=occ.get("evidence"),
                )

        for rel in other._store.get_all_relationships():
            self._store.add_relationship(
                resolved_names.get(rel.get("source", "").lower(), rel.get("source", "")),
                resolved_names.get(rel.get("target", "").lower(), rel.get("target", "")),
                rel.get("type", "related_to"),
                content_source=rel.get("content_source"),
                timestamp=rel.get("timestamp"),
                evidence=rel.get("evidence"),
                confidence=rel.get("confidence"),
            )

    def classify_for_planning(self):
        """Classify entities in this knowledge graph into planning taxonomy types."""
        from video_processor.integrators.taxonomy import TaxonomyClassifier

        classifier = TaxonomyClassifier(provider_manager=self.pm)
        entities = self._store.get_all_entities()
        relationships = self._store.get_all_relationships()
        return classifier.classify_entities(entities, relationships)

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
