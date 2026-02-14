"""Content cross-referencing between transcript and diagram entities."""

import logging
from typing import List, Optional

from video_processor.models import Entity, KeyPoint
from video_processor.providers.manager import ProviderManager
from video_processor.utils.json_parsing import parse_json_from_response

logger = logging.getLogger(__name__)


class ContentAnalyzer:
    """Cross-references transcript and diagram entities for richer knowledge."""

    def __init__(self, provider_manager: Optional[ProviderManager] = None):
        self.pm = provider_manager

    def cross_reference(
        self,
        transcript_entities: List[Entity],
        diagram_entities: List[Entity],
    ) -> List[Entity]:
        """
        Merge entities from transcripts and diagrams.

        Merges by exact name overlap first, then uses LLM for fuzzy matching
        of remaining entities. Adds source attribution.
        """
        merged: dict[str, Entity] = {}

        # Index transcript entities
        for e in transcript_entities:
            key = e.name.lower()
            merged[key] = Entity(
                name=e.name,
                type=e.type,
                descriptions=list(e.descriptions),
                source="transcript",
                occurrences=list(e.occurrences),
            )

        # Merge diagram entities
        for e in diagram_entities:
            key = e.name.lower()
            if key in merged:
                existing = merged[key]
                existing.source = "both"
                existing.descriptions = list(set(existing.descriptions + e.descriptions))
                existing.occurrences.extend(e.occurrences)
            else:
                merged[key] = Entity(
                    name=e.name,
                    type=e.type,
                    descriptions=list(e.descriptions),
                    source="diagram",
                    occurrences=list(e.occurrences),
                )

        # LLM fuzzy matching for unmatched entities
        if self.pm:
            unmatched_t = [
                e for e in transcript_entities if e.name.lower() not in {
                    d.name.lower() for d in diagram_entities
                }
            ]
            unmatched_d = [
                e for e in diagram_entities if e.name.lower() not in {
                    t.name.lower() for t in transcript_entities
                }
            ]

            if unmatched_t and unmatched_d:
                matches = self._fuzzy_match(unmatched_t, unmatched_d)
                for t_name, d_name in matches:
                    t_key = t_name.lower()
                    d_key = d_name.lower()
                    if t_key in merged and d_key in merged:
                        t_entity = merged[t_key]
                        d_entity = merged.pop(d_key)
                        t_entity.source = "both"
                        t_entity.descriptions = list(
                            set(t_entity.descriptions + d_entity.descriptions)
                        )
                        t_entity.occurrences.extend(d_entity.occurrences)

        return list(merged.values())

    def _fuzzy_match(
        self,
        transcript_entities: List[Entity],
        diagram_entities: List[Entity],
    ) -> List[tuple[str, str]]:
        """Use LLM to fuzzy-match entity names across sources."""
        if not self.pm:
            return []

        t_names = [e.name for e in transcript_entities]
        d_names = [e.name for e in diagram_entities]

        prompt = (
            "Match entities that refer to the same thing across these two lists.\n\n"
            f"Transcript entities: {t_names}\n"
            f"Diagram entities: {d_names}\n\n"
            "Return a JSON array of matched pairs:\n"
            '[{"transcript": "name from list 1", "diagram": "name from list 2"}]\n\n'
            "Only include confident matches. Return empty array if no matches.\n"
            "Return ONLY the JSON array."
        )

        try:
            raw = self.pm.chat([{"role": "user", "content": prompt}], temperature=0.2)
            parsed = parse_json_from_response(raw)
            if isinstance(parsed, list):
                return [
                    (item["transcript"], item["diagram"])
                    for item in parsed
                    if isinstance(item, dict) and "transcript" in item and "diagram" in item
                ]
        except Exception as e:
            logger.warning(f"Fuzzy matching failed: {e}")

        return []

    def enrich_key_points(
        self,
        key_points: List[KeyPoint],
        diagrams: list,
        transcript_text: str,
    ) -> List[KeyPoint]:
        """
        Link key points to relevant diagrams by entity overlap and temporal proximity.
        """
        if not diagrams:
            return key_points

        # Build diagram entity index
        diagram_entities: dict[int, set[str]] = {}
        for i, d in enumerate(diagrams):
            elements = d.get("elements", []) if isinstance(d, dict) else getattr(d, "elements", [])
            text = d.get("text_content", "") if isinstance(d, dict) else getattr(d, "text_content", "")
            entities = set(str(e).lower() for e in elements)
            if text:
                entities.update(word.lower() for word in text.split() if len(word) > 3)
            diagram_entities[i] = entities

        # Match key points to diagrams
        for kp in key_points:
            kp_words = set(kp.point.lower().split())
            if kp.details:
                kp_words.update(kp.details.lower().split())

            related = []
            for idx, d_entities in diagram_entities.items():
                overlap = kp_words & d_entities
                if len(overlap) >= 2:
                    related.append(idx)

            if related:
                kp.related_diagrams = related

        return key_points
