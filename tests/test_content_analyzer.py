"""Tests for content cross-referencing between transcript and diagram entities."""

import json
from unittest.mock import MagicMock

from video_processor.analyzers.content_analyzer import ContentAnalyzer
from video_processor.models import Entity, KeyPoint


class TestCrossReference:
    def test_exact_match_merges(self):
        analyzer = ContentAnalyzer()
        t_entities = [
            Entity(name="Python", type="concept", descriptions=["A language"]),
        ]
        d_entities = [
            Entity(name="Python", type="concept", descriptions=["A snake-named lang"]),
        ]
        result = analyzer.cross_reference(t_entities, d_entities)
        assert len(result) == 1
        assert result[0].source == "both"
        assert "A language" in result[0].descriptions
        assert "A snake-named lang" in result[0].descriptions

    def test_case_insensitive_merge(self):
        analyzer = ContentAnalyzer()
        t_entities = [Entity(name="Docker", type="technology", descriptions=["Containers"])]
        d_entities = [Entity(name="docker", type="technology", descriptions=["Container runtime"])]
        result = analyzer.cross_reference(t_entities, d_entities)
        assert len(result) == 1
        assert result[0].source == "both"

    def test_no_overlap_keeps_both(self):
        analyzer = ContentAnalyzer()
        t_entities = [Entity(name="Python", type="concept", descriptions=["Lang"])]
        d_entities = [Entity(name="Rust", type="concept", descriptions=["Systems"])]
        result = analyzer.cross_reference(t_entities, d_entities)
        assert len(result) == 2
        names = {e.name for e in result}
        assert names == {"Python", "Rust"}

    def test_transcript_only(self):
        analyzer = ContentAnalyzer()
        t_entities = [Entity(name="Foo", type="concept")]
        result = analyzer.cross_reference(t_entities, [])
        assert len(result) == 1
        assert result[0].source == "transcript"

    def test_diagram_only(self):
        analyzer = ContentAnalyzer()
        d_entities = [Entity(name="Bar", type="concept")]
        result = analyzer.cross_reference([], d_entities)
        assert len(result) == 1
        assert result[0].source == "diagram"

    def test_empty_inputs(self):
        analyzer = ContentAnalyzer()
        result = analyzer.cross_reference([], [])
        assert result == []

    def test_occurrences_merged(self):
        analyzer = ContentAnalyzer()
        t_entities = [
            Entity(name="API", type="concept", occurrences=[{"source": "transcript", "ts": 10}]),
        ]
        d_entities = [
            Entity(name="API", type="concept", occurrences=[{"source": "diagram", "ts": 20}]),
        ]
        result = analyzer.cross_reference(t_entities, d_entities)
        assert len(result) == 1
        assert len(result[0].occurrences) == 2


class TestFuzzyMatch:
    def test_fuzzy_match_with_llm(self):
        pm = MagicMock()
        pm.chat.return_value = json.dumps(
            [
                {"transcript": "K8s", "diagram": "Kubernetes"},
            ]
        )
        analyzer = ContentAnalyzer(provider_manager=pm)

        t_entities = [
            Entity(name="K8s", type="technology", descriptions=["Container orchestration"]),
        ]
        d_entities = [
            Entity(name="Kubernetes", type="technology", descriptions=["K8s system"]),
        ]
        result = analyzer.cross_reference(t_entities, d_entities)

        # Fuzzy match should merge these
        assert len(result) == 1
        assert result[0].source == "both"
        assert result[0].name == "K8s"

    def test_fuzzy_match_no_matches(self):
        pm = MagicMock()
        pm.chat.return_value = "[]"
        analyzer = ContentAnalyzer(provider_manager=pm)

        t_entities = [Entity(name="Alpha", type="concept")]
        d_entities = [Entity(name="Beta", type="concept")]
        result = analyzer.cross_reference(t_entities, d_entities)
        assert len(result) == 2

    def test_fuzzy_match_llm_error(self):
        pm = MagicMock()
        pm.chat.side_effect = Exception("API error")
        analyzer = ContentAnalyzer(provider_manager=pm)

        t_entities = [Entity(name="X", type="concept")]
        d_entities = [Entity(name="Y", type="concept")]
        result = analyzer.cross_reference(t_entities, d_entities)
        # Should still return both entities despite error
        assert len(result) == 2

    def test_fuzzy_match_bad_json(self):
        pm = MagicMock()
        pm.chat.return_value = "not json at all"
        analyzer = ContentAnalyzer(provider_manager=pm)

        t_entities = [Entity(name="A", type="concept")]
        d_entities = [Entity(name="B", type="concept")]
        result = analyzer.cross_reference(t_entities, d_entities)
        assert len(result) == 2

    def test_fuzzy_match_skipped_without_provider(self):
        analyzer = ContentAnalyzer()
        t_entities = [Entity(name="ML", type="concept")]
        d_entities = [Entity(name="Machine Learning", type="concept")]
        result = analyzer.cross_reference(t_entities, d_entities)
        # No LLM so no fuzzy matching — both remain separate
        assert len(result) == 2

    def test_fuzzy_match_skipped_when_all_exact(self):
        pm = MagicMock()
        analyzer = ContentAnalyzer(provider_manager=pm)

        t_entities = [Entity(name="Same", type="concept")]
        d_entities = [Entity(name="Same", type="concept")]
        result = analyzer.cross_reference(t_entities, d_entities)
        # All matched exactly — no fuzzy match call needed
        pm.chat.assert_not_called()
        assert len(result) == 1


class TestEnrichKeyPoints:
    def test_enriches_with_matching_diagrams(self):
        analyzer = ContentAnalyzer()
        kps = [
            KeyPoint(point="The deployment pipeline uses Docker containers"),
        ]
        diagrams = [
            {"elements": ["Docker", "Pipeline", "Build"], "text_content": "CI/CD flow"},
        ]
        result = analyzer.enrich_key_points(kps, diagrams, "")
        assert len(result) == 1
        assert result[0].related_diagrams == [0]

    def test_no_match_below_threshold(self):
        analyzer = ContentAnalyzer()
        kps = [
            KeyPoint(point="Meeting scheduled for Friday"),
        ]
        diagrams = [
            {"elements": ["Docker", "Pipeline"], "text_content": "Architecture diagram"},
        ]
        result = analyzer.enrich_key_points(kps, diagrams, "")
        assert result[0].related_diagrams == []

    def test_empty_diagrams_returns_unchanged(self):
        analyzer = ContentAnalyzer()
        kps = [KeyPoint(point="Test point")]
        result = analyzer.enrich_key_points(kps, [], "")
        assert len(result) == 1
        assert result[0].related_diagrams == []

    def test_multiple_diagram_matches(self):
        analyzer = ContentAnalyzer()
        kps = [
            KeyPoint(point="Database migration requires testing schema changes"),
        ]
        diagrams = [
            {"elements": ["Database", "Schema", "Migration"], "text_content": ""},
            {"elements": ["Testing", "Schema", "Validation"], "text_content": ""},
        ]
        result = analyzer.enrich_key_points(kps, diagrams, "")
        assert len(result[0].related_diagrams) == 2

    def test_details_used_for_matching(self):
        analyzer = ContentAnalyzer()
        kps = [
            KeyPoint(
                point="Architecture overview", details="Uses Docker and Kubernetes for deployment"
            ),
        ]
        diagrams = [
            {"elements": ["Docker", "Kubernetes"], "text_content": "deployment infrastructure"},
        ]
        result = analyzer.enrich_key_points(kps, diagrams, "")
        assert 0 in result[0].related_diagrams

    def test_diagram_as_object_with_attrs(self):
        analyzer = ContentAnalyzer()

        class FakeDiagram:
            elements = ["Alpha", "Beta"]
            text_content = "some relevant content"

        kps = [KeyPoint(point="Alpha Beta interaction patterns")]
        result = analyzer.enrich_key_points(kps, [FakeDiagram()], "")
        assert result[0].related_diagrams == [0]
