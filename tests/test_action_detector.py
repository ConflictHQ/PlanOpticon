"""Tests for enhanced action item detection."""

import json
from unittest.mock import MagicMock

import pytest

from video_processor.analyzers.action_detector import ActionDetector
from video_processor.models import ActionItem, TranscriptSegment


class TestPatternExtract:
    def test_detects_need_to(self):
        detector = ActionDetector()
        items = detector.detect_from_transcript("We need to update the database schema before release.")
        assert len(items) >= 1
        assert any("database" in i.action.lower() for i in items)

    def test_detects_should(self):
        detector = ActionDetector()
        items = detector.detect_from_transcript("Alice should review the pull request by Friday.")
        assert len(items) >= 1

    def test_detects_action_item_keyword(self):
        detector = ActionDetector()
        items = detector.detect_from_transcript("Action item: set up monitoring for the new service.")
        assert len(items) >= 1

    def test_detects_follow_up(self):
        detector = ActionDetector()
        items = detector.detect_from_transcript("Follow up with the client about requirements.")
        assert len(items) >= 1

    def test_detects_lets(self):
        detector = ActionDetector()
        items = detector.detect_from_transcript("Let's schedule a meeting to discuss the roadmap.")
        assert len(items) >= 1

    def test_ignores_short_sentences(self):
        detector = ActionDetector()
        items = detector.detect_from_transcript("Do it.")
        assert len(items) == 0

    def test_no_action_patterns(self):
        detector = ActionDetector()
        items = detector.detect_from_transcript(
            "The weather was nice today. We had lunch at noon."
        )
        assert len(items) == 0

    def test_multiple_sentences(self):
        detector = ActionDetector()
        text = (
            "We need to deploy the fix. "
            "Alice should test it first. "
            "The sky is blue."
        )
        items = detector.detect_from_transcript(text)
        assert len(items) == 2

    def test_source_is_transcript(self):
        detector = ActionDetector()
        items = detector.detect_from_transcript("We need to fix the authentication module.")
        for item in items:
            assert item.source == "transcript"


class TestLLMExtract:
    def test_llm_extraction(self):
        pm = MagicMock()
        pm.chat.return_value = json.dumps([
            {"action": "Deploy new version", "assignee": "Bob", "deadline": "Friday",
             "priority": "high", "context": "Production release"}
        ])
        detector = ActionDetector(provider_manager=pm)
        items = detector.detect_from_transcript("Deploy new version by Friday.")
        assert len(items) == 1
        assert items[0].action == "Deploy new version"
        assert items[0].assignee == "Bob"
        assert items[0].deadline == "Friday"
        assert items[0].priority == "high"
        assert items[0].source == "transcript"

    def test_llm_returns_empty(self):
        pm = MagicMock()
        pm.chat.return_value = "[]"
        detector = ActionDetector(provider_manager=pm)
        items = detector.detect_from_transcript("No action items here.")
        assert items == []

    def test_llm_error_returns_empty(self):
        pm = MagicMock()
        pm.chat.side_effect = Exception("API error")
        detector = ActionDetector(provider_manager=pm)
        items = detector.detect_from_transcript("We need to fix this.")
        assert items == []

    def test_llm_bad_json(self):
        pm = MagicMock()
        pm.chat.return_value = "not valid json"
        detector = ActionDetector(provider_manager=pm)
        items = detector.detect_from_transcript("Update the docs.")
        assert items == []

    def test_llm_skips_items_without_action(self):
        pm = MagicMock()
        pm.chat.return_value = json.dumps([
            {"action": "Valid action", "assignee": None},
            {"assignee": "Alice"},  # No action field
            {"action": "", "assignee": "Bob"},  # Empty action
        ])
        detector = ActionDetector(provider_manager=pm)
        items = detector.detect_from_transcript("Some text.")
        assert len(items) == 1
        assert items[0].action == "Valid action"


class TestDetectFromDiagrams:
    def test_dict_diagrams(self):
        pm = MagicMock()
        pm.chat.return_value = json.dumps([
            {"action": "Migrate database", "assignee": None, "deadline": None,
             "priority": None, "context": None},
        ])
        detector = ActionDetector(provider_manager=pm)
        diagrams = [
            {"text_content": "Step 1: Migrate database", "elements": ["DB", "Migration"]},
        ]
        items = detector.detect_from_diagrams(diagrams)
        assert len(items) == 1
        assert items[0].source == "diagram"

    def test_object_diagrams(self):
        pm = MagicMock()
        pm.chat.return_value = json.dumps([
            {"action": "Update API", "assignee": None, "deadline": None,
             "priority": None, "context": None},
        ])
        detector = ActionDetector(provider_manager=pm)

        class FakeDiagram:
            text_content = "Update API endpoints"
            elements = ["API", "Gateway"]

        items = detector.detect_from_diagrams([FakeDiagram()])
        assert len(items) >= 1
        assert items[0].source == "diagram"

    def test_empty_diagram_skipped(self):
        detector = ActionDetector()
        diagrams = [{"text_content": "", "elements": []}]
        items = detector.detect_from_diagrams(diagrams)
        assert items == []

    def test_pattern_fallback_for_diagrams(self):
        detector = ActionDetector()  # No provider
        diagrams = [
            {"text_content": "We need to update the configuration before deployment.", "elements": []},
        ]
        items = detector.detect_from_diagrams(diagrams)
        assert len(items) >= 1
        assert items[0].source == "diagram"


class TestMergeActionItems:
    def test_deduplicates(self):
        detector = ActionDetector()
        t_items = [ActionItem(action="Deploy fix", source="transcript")]
        d_items = [ActionItem(action="Deploy fix", source="diagram")]
        merged = detector.merge_action_items(t_items, d_items)
        assert len(merged) == 1

    def test_case_insensitive_dedup(self):
        detector = ActionDetector()
        t_items = [ActionItem(action="deploy fix", source="transcript")]
        d_items = [ActionItem(action="Deploy Fix", source="diagram")]
        merged = detector.merge_action_items(t_items, d_items)
        assert len(merged) == 1

    def test_keeps_unique(self):
        detector = ActionDetector()
        t_items = [ActionItem(action="Task A", source="transcript")]
        d_items = [ActionItem(action="Task B", source="diagram")]
        merged = detector.merge_action_items(t_items, d_items)
        assert len(merged) == 2

    def test_empty_inputs(self):
        detector = ActionDetector()
        merged = detector.merge_action_items([], [])
        assert merged == []


class TestAttachTimestamps:
    def test_attaches_matching_segment(self):
        detector = ActionDetector()
        items = [
            ActionItem(action="We need to update the database schema before release"),
        ]
        segments = [
            TranscriptSegment(start=0.0, end=5.0, text="Welcome to the meeting."),
            TranscriptSegment(start=5.0, end=15.0, text="We need to update the database schema before release."),
            TranscriptSegment(start=15.0, end=20.0, text="Any questions?"),
        ]
        detector.detect_from_transcript(
            "We need to update the database schema before release.",
            segments=segments,
        )
        # Pattern extract will create items; check them
        result = detector.detect_from_transcript(
            "We need to update the database schema before release.",
            segments=segments,
        )
        assert len(result) >= 1
        # Context should be set with timestamp
        assert any(i.context and "5s" in i.context for i in result)

    def test_no_match_no_context(self):
        detector = ActionDetector()
        items = [ActionItem(action="Completely unrelated action")]
        segments = [
            TranscriptSegment(start=0.0, end=5.0, text="Hello world."),
        ]
        # Manually test the private method
        detector._attach_timestamps(items, segments)
        assert items[0].context is None
