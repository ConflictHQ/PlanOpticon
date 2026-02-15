"""Enhanced action item detection from transcripts and diagrams."""

import logging
import re
from typing import List, Optional

from video_processor.models import ActionItem, TranscriptSegment
from video_processor.providers.manager import ProviderManager
from video_processor.utils.json_parsing import parse_json_from_response

logger = logging.getLogger(__name__)

# Patterns that indicate action items in natural language
_ACTION_PATTERNS = [
    re.compile(r"\b(?:need|needs)\s+to\b", re.IGNORECASE),
    re.compile(r"\b(?:should|must|shall)\s+\w+", re.IGNORECASE),
    re.compile(r"\b(?:will|going\s+to)\s+\w+", re.IGNORECASE),
    re.compile(r"\b(?:action\s+item|todo|to-do|follow[\s-]?up)\b", re.IGNORECASE),
    re.compile(r"\b(?:assigned?\s+to|responsible\s+for)\b", re.IGNORECASE),
    re.compile(r"\b(?:deadline|due\s+(?:date|by))\b", re.IGNORECASE),
    re.compile(r"\b(?:let'?s|let\s+us)\s+\w+", re.IGNORECASE),
    re.compile(r"\b(?:make\s+sure|ensure)\b", re.IGNORECASE),
    re.compile(r"\b(?:can\s+you|could\s+you|please)\s+\w+", re.IGNORECASE),
]


class ActionDetector:
    """Detects action items from transcripts using heuristics and LLM."""

    def __init__(self, provider_manager: Optional[ProviderManager] = None):
        self.pm = provider_manager

    def detect_from_transcript(
        self,
        text: str,
        segments: Optional[List[TranscriptSegment]] = None,
    ) -> List[ActionItem]:
        """
        Detect action items from transcript text.

        Uses LLM extraction when available, falls back to pattern matching.
        Segments are used to attach timestamps.
        """
        if self.pm:
            items = self._llm_extract(text)
        else:
            items = self._pattern_extract(text)

        # Attach timestamps from segments if available
        if segments and items:
            self._attach_timestamps(items, segments)

        return items

    def detect_from_diagrams(
        self,
        diagrams: list,
    ) -> List[ActionItem]:
        """
        Extract action items mentioned in diagram text content.

        Looks for action-oriented language in diagram text/elements.
        """
        items: List[ActionItem] = []

        for diagram in diagrams:
            text = ""
            if isinstance(diagram, dict):
                text = diagram.get("text_content", "") or ""
                elements = diagram.get("elements", [])
            else:
                text = getattr(diagram, "text_content", "") or ""
                elements = getattr(diagram, "elements", [])

            combined = text + " " + " ".join(str(e) for e in elements)
            if not combined.strip():
                continue

            if self.pm:
                diagram_items = self._llm_extract(combined)
            else:
                diagram_items = self._pattern_extract(combined)

            for item in diagram_items:
                item.source = "diagram"
            items.extend(diagram_items)

        return items

    def merge_action_items(
        self,
        transcript_items: List[ActionItem],
        diagram_items: List[ActionItem],
    ) -> List[ActionItem]:
        """
        Merge action items from transcript and diagram sources.

        Deduplicates by checking for similar action text.
        """
        merged: List[ActionItem] = list(transcript_items)
        existing_actions = {a.action.lower().strip() for a in merged}

        for item in diagram_items:
            normalized = item.action.lower().strip()
            if normalized not in existing_actions:
                merged.append(item)
                existing_actions.add(normalized)

        return merged

    def _llm_extract(self, text: str) -> List[ActionItem]:
        """Extract action items using LLM."""
        if not self.pm:
            return []

        prompt = (
            "Extract all action items, tasks, and commitments "
            "from the following text.\n\n"
            f"TEXT:\n{text[:8000]}\n\n"
            "Return a JSON array:\n"
            '[{"action": "...", "assignee": "...", "deadline": "...", '
            '"priority": "...", "context": "..."}]\n\n'
            "Only include clear, actionable items. "
            "Set fields to null if not mentioned.\n"
            "Return ONLY the JSON array."
        )

        try:
            raw = self.pm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            parsed = parse_json_from_response(raw)
            if isinstance(parsed, list):
                return [
                    ActionItem(
                        action=item.get("action", ""),
                        assignee=item.get("assignee"),
                        deadline=item.get("deadline"),
                        priority=item.get("priority"),
                        context=item.get("context"),
                        source="transcript",
                    )
                    for item in parsed
                    if isinstance(item, dict) and item.get("action")
                ]
        except Exception as e:
            logger.warning(f"LLM action extraction failed: {e}")

        return []

    def _pattern_extract(self, text: str) -> List[ActionItem]:
        """Extract action items using regex pattern matching."""
        items: List[ActionItem] = []
        sentences = re.split(r"[.!?]\s+", text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence or len(sentence) < 10:
                continue

            for pattern in _ACTION_PATTERNS:
                if pattern.search(sentence):
                    items.append(
                        ActionItem(
                            action=sentence,
                            source="transcript",
                        )
                    )
                    break  # One match per sentence is enough

        return items

    def _attach_timestamps(
        self,
        items: List[ActionItem],
        segments: List[TranscriptSegment],
    ) -> None:
        """Attach timestamps to action items by finding matching segments."""
        for item in items:
            action_lower = item.action.lower()
            best_overlap = 0
            best_segment = None

            for seg in segments:
                seg_lower = seg.text.lower()
                # Check word overlap
                action_words = set(action_lower.split())
                seg_words = set(seg_lower.split())
                overlap = len(action_words & seg_words)

                if overlap > best_overlap:
                    best_overlap = overlap
                    best_segment = seg

            if best_segment and best_overlap >= 3:
                if not item.context:
                    item.context = f"at {best_segment.start:.0f}s"
