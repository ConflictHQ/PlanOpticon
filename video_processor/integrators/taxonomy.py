"""Taxonomy classifier for planning entity extraction.

Bridges raw knowledge graph entities (person, technology, concept) into
planning-ready structures (goals, requirements, decisions, risks).
"""

import logging
from typing import Any, Dict, List, Optional

from video_processor.models import PlanningEntity, PlanningEntityType

logger = logging.getLogger(__name__)

# Keyword rules for heuristic classification.  Each tuple is
# (PlanningEntityType, list-of-keywords).  Order matters — first match wins.
_KEYWORD_RULES: List[tuple] = [
    (PlanningEntityType.GOAL, ["goal", "objective", "aim", "target outcome"]),
    (
        PlanningEntityType.REQUIREMENT,
        ["must", "should", "requirement", "need", "required"],
    ),
    (
        PlanningEntityType.CONSTRAINT,
        ["constraint", "limitation", "restrict", "cannot", "must not"],
    ),
    (
        PlanningEntityType.DECISION,
        ["decided", "decision", "chose", "selected", "agreed"],
    ),
    (PlanningEntityType.RISK, ["risk", "concern", "worry", "danger", "threat"]),
    (
        PlanningEntityType.ASSUMPTION,
        ["assume", "assumption", "expecting", "presume"],
    ),
    (
        PlanningEntityType.DEPENDENCY,
        ["depends", "dependency", "relies on", "prerequisite", "blocked"],
    ),
    (
        PlanningEntityType.MILESTONE,
        ["milestone", "deadline", "deliverable", "release", "launch"],
    ),
    (
        PlanningEntityType.TASK,
        ["task", "todo", "action item", "work item", "implement"],
    ),
    (PlanningEntityType.FEATURE, ["feature", "capability", "functionality"]),
]


class TaxonomyClassifier:
    """Classifies raw knowledge graph entities into planning taxonomy types."""

    def __init__(self, provider_manager: Optional[Any] = None):
        self.pm = provider_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_entities(
        self,
        entities: List[Dict],
        relationships: List[Dict],
    ) -> List[PlanningEntity]:
        """Classify extracted entities into planning entity types.

        Uses heuristic classification first, then LLM refinement if a
        provider manager is available.
        """
        planning_entities: List[PlanningEntity] = []

        # Step 1: heuristic classification
        for entity in entities:
            planning_type = self._heuristic_classify(entity, relationships)
            if planning_type:
                descs = entity.get("descriptions", [])
                planning_entities.append(
                    PlanningEntity(
                        name=entity["name"],
                        planning_type=planning_type,
                        description="; ".join(descs[:2]),
                        source_entities=[entity["name"]],
                    )
                )

        # Step 2: LLM refinement (if provider available)
        if self.pm and entities:
            llm_classified = self._llm_classify(entities, relationships)
            planning_entities = self._merge_classifications(planning_entities, llm_classified)

        return planning_entities

    def organize_by_workstream(
        self, planning_entities: List[PlanningEntity]
    ) -> Dict[str, List[PlanningEntity]]:
        """Group planning entities into logical workstreams by type."""
        workstreams: Dict[str, List[PlanningEntity]] = {}
        for pe in planning_entities:
            group = pe.planning_type.value + "s"
            workstreams.setdefault(group, []).append(pe)
        return workstreams

    # ------------------------------------------------------------------
    # Heuristic classification
    # ------------------------------------------------------------------

    def _heuristic_classify(
        self,
        entity: Dict,
        relationships: List[Dict],  # noqa: ARG002 — reserved for future rules
    ) -> Optional[PlanningEntityType]:
        """Rule-based classification from entity type and description keywords."""
        desc_lower = " ".join(entity.get("descriptions", [])).lower()

        for planning_type, keywords in _KEYWORD_RULES:
            if any(kw in desc_lower for kw in keywords):
                return planning_type

        return None

    # ------------------------------------------------------------------
    # LLM classification
    # ------------------------------------------------------------------

    def _llm_classify(
        self, entities: List[Dict], relationships: List[Dict]
    ) -> List[PlanningEntity]:
        """Use LLM to classify entities into planning types."""
        entity_summaries = []
        for e in entities[:50]:  # limit to avoid token overflow
            descs = e.get("descriptions", [])
            desc_str = "; ".join(descs[:2]) if descs else "no description"
            entity_summaries.append(f"- {e['name']} ({e.get('type', 'concept')}): {desc_str}")

        prompt = (
            "Classify these entities from a knowledge graph into planning categories.\n\n"
            "Entities:\n" + "\n".join(entity_summaries) + "\n\n"
            "Categories: goal, requirement, constraint, decision, risk, assumption, "
            "dependency, milestone, task, feature\n\n"
            "For each entity that fits a planning category, return JSON:\n"
            '[{"name": "...", "planning_type": "...", "priority": "high|medium|low"}]\n\n'
            "Only include entities that clearly fit a planning category. "
            "Skip entities that are just people, technologies, or general concepts. "
            "Return ONLY the JSON array."
        )

        try:
            raw = self.pm.chat(
                [{"role": "user", "content": prompt}],
                max_tokens=2048,
                temperature=0.2,
            )
        except Exception:
            logger.warning("LLM classification failed, using heuristic only")
            return []

        from video_processor.utils.json_parsing import parse_json_from_response

        parsed = parse_json_from_response(raw)

        results: List[PlanningEntity] = []
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict) and "name" in item and "planning_type" in item:
                    try:
                        ptype = PlanningEntityType(item["planning_type"])
                        results.append(
                            PlanningEntity(
                                name=item["name"],
                                planning_type=ptype,
                                priority=item.get("priority"),
                                source_entities=[item["name"]],
                            )
                        )
                    except ValueError:
                        pass
        return results

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_classifications(
        heuristic: List[PlanningEntity],
        llm: List[PlanningEntity],
    ) -> List[PlanningEntity]:
        """Merge heuristic and LLM classifications. LLM wins on conflicts."""
        by_name = {pe.name.lower(): pe for pe in heuristic}
        for pe in llm:
            by_name[pe.name.lower()] = pe  # LLM overrides
        return list(by_name.values())
