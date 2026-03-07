"""Tests for the planning taxonomy classifier."""

from unittest.mock import MagicMock

from video_processor.integrators.taxonomy import TaxonomyClassifier
from video_processor.models import (
    PlanningEntity,
    PlanningEntityType,
    PlanningRelationshipType,
)

# ── Fixtures ──────────────────────────────────────────────────────────


def _entity(name, descriptions=None, entity_type="concept"):
    return {
        "name": name,
        "type": entity_type,
        "descriptions": descriptions or [],
    }


# ── PlanningEntityType enum ──────────────────────────────────────────


class TestPlanningEntityType:
    def test_all_values(self):
        expected = {
            "goal",
            "requirement",
            "constraint",
            "decision",
            "risk",
            "assumption",
            "dependency",
            "milestone",
            "task",
            "feature",
        }
        assert {t.value for t in PlanningEntityType} == expected

    def test_str_enum(self):
        assert PlanningEntityType.GOAL == "goal"
        assert PlanningEntityType.RISK.value == "risk"


class TestPlanningRelationshipType:
    def test_all_values(self):
        expected = {
            "requires",
            "blocked_by",
            "has_risk",
            "depends_on",
            "addresses",
            "has_tradeoff",
            "delivers",
            "implements",
            "parent_of",
        }
        assert {t.value for t in PlanningRelationshipType} == expected


# ── PlanningEntity model ─────────────────────────────────────────────


class TestPlanningEntity:
    def test_minimal(self):
        pe = PlanningEntity(name="Ship v2", planning_type=PlanningEntityType.GOAL)
        assert pe.description == ""
        assert pe.priority is None
        assert pe.status is None
        assert pe.source_entities == []
        assert pe.metadata == {}

    def test_full(self):
        pe = PlanningEntity(
            name="Ship v2",
            planning_type=PlanningEntityType.GOAL,
            description="Release version 2",
            priority="high",
            status="identified",
            source_entities=["v2 release"],
            metadata={"quarter": "Q3"},
        )
        assert pe.priority == "high"
        assert pe.metadata["quarter"] == "Q3"

    def test_round_trip(self):
        pe = PlanningEntity(
            name="Auth module",
            planning_type=PlanningEntityType.FEATURE,
            priority="medium",
            source_entities=["Auth"],
        )
        restored = PlanningEntity.model_validate_json(pe.model_dump_json())
        assert restored == pe


# ── Heuristic classification ─────────────────────────────────────────


class TestHeuristicClassify:
    def setup_method(self):
        self.classifier = TaxonomyClassifier()

    def test_goal_keyword(self):
        entities = [_entity("Ship v2", ["Our main goal is to ship v2"])]
        result = self.classifier.classify_entities(entities, [])
        assert len(result) == 1
        assert result[0].planning_type == PlanningEntityType.GOAL

    def test_requirement_keyword(self):
        entities = [_entity("Auth", ["System must support SSO"])]
        result = self.classifier.classify_entities(entities, [])
        assert result[0].planning_type == PlanningEntityType.REQUIREMENT

    def test_constraint_keyword(self):
        entities = [_entity("Budget", ["Budget limitation of $50k"])]
        result = self.classifier.classify_entities(entities, [])
        assert result[0].planning_type == PlanningEntityType.CONSTRAINT

    def test_decision_keyword(self):
        entities = [_entity("DB choice", ["Team decided to use Postgres"])]
        result = self.classifier.classify_entities(entities, [])
        assert result[0].planning_type == PlanningEntityType.DECISION

    def test_risk_keyword(self):
        entities = [_entity("Vendor lock-in", ["There is a risk of vendor lock-in"])]
        result = self.classifier.classify_entities(entities, [])
        assert result[0].planning_type == PlanningEntityType.RISK

    def test_assumption_keyword(self):
        entities = [_entity("Team size", ["We assume the team stays at 5"])]
        result = self.classifier.classify_entities(entities, [])
        assert result[0].planning_type == PlanningEntityType.ASSUMPTION

    def test_dependency_keyword(self):
        entities = [_entity("API v3", ["This depends on API v3 being ready"])]
        result = self.classifier.classify_entities(entities, [])
        assert result[0].planning_type == PlanningEntityType.DEPENDENCY

    def test_milestone_keyword(self):
        entities = [_entity("Beta", ["Beta release milestone in March"])]
        result = self.classifier.classify_entities(entities, [])
        assert result[0].planning_type == PlanningEntityType.MILESTONE

    def test_task_keyword(self):
        entities = [_entity("Setup CI", ["Action item: set up CI pipeline"])]
        result = self.classifier.classify_entities(entities, [])
        assert result[0].planning_type == PlanningEntityType.TASK

    def test_feature_keyword(self):
        entities = [_entity("Search", ["Search feature with autocomplete"])]
        result = self.classifier.classify_entities(entities, [])
        assert result[0].planning_type == PlanningEntityType.FEATURE

    def test_no_match(self):
        entities = [_entity("Python", ["A programming language"])]
        result = self.classifier.classify_entities(entities, [])
        assert len(result) == 0

    def test_multiple_entities(self):
        entities = [
            _entity("Goal A", ["The goal is performance"]),
            _entity("Person B", ["Engineer on the team"], "person"),
            _entity("Risk C", ["Risk of data loss"]),
        ]
        result = self.classifier.classify_entities(entities, [])
        assert len(result) == 2
        types = {pe.planning_type for pe in result}
        assert PlanningEntityType.GOAL in types
        assert PlanningEntityType.RISK in types

    def test_description_joined(self):
        entities = [_entity("Perf", ["System must handle", "1000 req/s"])]
        result = self.classifier.classify_entities(entities, [])
        assert result[0].planning_type == PlanningEntityType.REQUIREMENT
        assert result[0].description == "System must handle; 1000 req/s"

    def test_source_entities_populated(self):
        entities = [_entity("Ship v2", ["Our main goal"])]
        result = self.classifier.classify_entities(entities, [])
        assert result[0].source_entities == ["Ship v2"]


# ── LLM classification ───────────────────────────────────────────────


class TestLLMClassify:
    def test_llm_results_merged(self):
        mock_pm = MagicMock()
        mock_pm.chat.return_value = (
            '[{"name": "Python", "planning_type": "feature", "priority": "medium"}]'
        )
        classifier = TaxonomyClassifier(provider_manager=mock_pm)
        entities = [_entity("Python", ["A programming language"])]
        result = classifier.classify_entities(entities, [])
        assert len(result) == 1
        assert result[0].planning_type == PlanningEntityType.FEATURE
        assert result[0].priority == "medium"

    def test_llm_overrides_heuristic(self):
        mock_pm = MagicMock()
        # Heuristic would say REQUIREMENT ("must"), LLM says GOAL
        mock_pm.chat.return_value = (
            '[{"name": "Perf", "planning_type": "goal", "priority": "high"}]'
        )
        classifier = TaxonomyClassifier(provider_manager=mock_pm)
        entities = [_entity("Perf", ["System must be fast"])]
        result = classifier.classify_entities(entities, [])
        assert len(result) == 1
        assert result[0].planning_type == PlanningEntityType.GOAL

    def test_llm_invalid_type_skipped(self):
        mock_pm = MagicMock()
        mock_pm.chat.return_value = (
            '[{"name": "X", "planning_type": "not_a_type", "priority": "low"}]'
        )
        classifier = TaxonomyClassifier(provider_manager=mock_pm)
        entities = [_entity("X", ["Something"])]
        result = classifier.classify_entities(entities, [])
        assert len(result) == 0

    def test_llm_failure_falls_back(self):
        mock_pm = MagicMock()
        mock_pm.chat.side_effect = RuntimeError("API down")
        classifier = TaxonomyClassifier(provider_manager=mock_pm)
        entities = [_entity("Ship v2", ["Our goal"])]
        result = classifier.classify_entities(entities, [])
        # Should still get heuristic result
        assert len(result) == 1
        assert result[0].planning_type == PlanningEntityType.GOAL

    def test_llm_empty_response(self):
        mock_pm = MagicMock()
        mock_pm.chat.return_value = ""
        classifier = TaxonomyClassifier(provider_manager=mock_pm)
        entities = [_entity("Ship v2", ["Our goal"])]
        result = classifier.classify_entities(entities, [])
        assert len(result) == 1  # heuristic still works


# ── Workstream organization ──────────────────────────────────────────


class TestOrganizeByWorkstream:
    def test_groups_by_type(self):
        classifier = TaxonomyClassifier()
        entities = [
            PlanningEntity(name="A", planning_type=PlanningEntityType.GOAL),
            PlanningEntity(name="B", planning_type=PlanningEntityType.GOAL),
            PlanningEntity(name="C", planning_type=PlanningEntityType.RISK),
        ]
        ws = classifier.organize_by_workstream(entities)
        assert len(ws["goals"]) == 2
        assert len(ws["risks"]) == 1

    def test_empty_input(self):
        classifier = TaxonomyClassifier()
        ws = classifier.organize_by_workstream([])
        assert ws == {}


# ── Merge classifications ────────────────────────────────────────────


class TestMergeClassifications:
    def test_llm_wins_conflict(self):
        h = [PlanningEntity(name="X", planning_type=PlanningEntityType.GOAL)]
        llm_list = [PlanningEntity(name="X", planning_type=PlanningEntityType.RISK)]
        merged = TaxonomyClassifier._merge_classifications(h, llm_list)
        assert len(merged) == 1
        assert merged[0].planning_type == PlanningEntityType.RISK

    def test_case_insensitive_merge(self):
        h = [PlanningEntity(name="Auth", planning_type=PlanningEntityType.FEATURE)]
        llm_list = [PlanningEntity(name="auth", planning_type=PlanningEntityType.REQUIREMENT)]
        merged = TaxonomyClassifier._merge_classifications(h, llm_list)
        assert len(merged) == 1
        assert merged[0].planning_type == PlanningEntityType.REQUIREMENT

    def test_union_of_distinct(self):
        h = [PlanningEntity(name="A", planning_type=PlanningEntityType.GOAL)]
        llm_list = [PlanningEntity(name="B", planning_type=PlanningEntityType.RISK)]
        merged = TaxonomyClassifier._merge_classifications(h, llm_list)
        assert len(merged) == 2
