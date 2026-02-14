"""Tests for prompt template management."""

import pytest

from video_processor.utils.prompt_templates import (
    DEFAULT_TEMPLATES,
    PromptTemplate,
    default_prompt_manager,
)


class TestPromptTemplate:
    def test_default_templates_loaded(self):
        pm = PromptTemplate(default_templates=DEFAULT_TEMPLATES)
        assert len(pm.templates) == 10

    def test_all_expected_templates_exist(self):
        expected = [
            "content_analysis",
            "diagram_extraction",
            "action_item_detection",
            "content_summary",
            "summary_generation",
            "key_points_extraction",
            "entity_extraction",
            "relationship_extraction",
            "diagram_analysis",
            "mermaid_generation",
        ]
        for name in expected:
            assert name in DEFAULT_TEMPLATES, f"Missing template: {name}"

    def test_get_template(self):
        pm = PromptTemplate(default_templates={"test": "Hello $name"})
        template = pm.get_template("test")
        assert template is not None

    def test_get_missing_template(self):
        pm = PromptTemplate(default_templates={})
        assert pm.get_template("nonexistent") is None

    def test_format_prompt(self):
        pm = PromptTemplate(default_templates={"greet": "Hello $name, welcome to $place"})
        result = pm.format_prompt("greet", name="Alice", place="Wonderland")
        assert "Alice" in result
        assert "Wonderland" in result

    def test_format_missing_template(self):
        pm = PromptTemplate(default_templates={})
        result = pm.format_prompt("nonexistent", key="value")
        assert result is None

    def test_safe_substitute_missing_vars(self):
        pm = PromptTemplate(default_templates={"test": "Hello $name and $other"})
        result = pm.format_prompt("test", name="Alice")
        assert "Alice" in result
        assert "$other" in result  # safe_substitute keeps unresolved vars

    def test_add_template(self):
        pm = PromptTemplate(default_templates={})
        pm.add_template("new", "New template: $var")
        result = pm.format_prompt("new", var="value")
        assert "value" in result

    def test_save_template_no_dir(self):
        pm = PromptTemplate(default_templates={"test": "content"})
        assert pm.save_template("test") is False

    def test_save_template_missing_name(self):
        pm = PromptTemplate(default_templates={})
        assert pm.save_template("nonexistent") is False

    def test_save_and_load_from_dir(self, tmp_path):
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        (templates_dir / "custom.txt").write_text("Custom: $data")

        pm = PromptTemplate(templates_dir=templates_dir)
        assert "custom" in pm.templates
        result = pm.format_prompt("custom", data="hello")
        assert "hello" in result

    def test_save_template_to_dir(self, tmp_path):
        templates_dir = tmp_path / "templates"
        pm = PromptTemplate(
            templates_dir=templates_dir,
            default_templates={"saveme": "Save this: $x"},
        )
        result = pm.save_template("saveme")
        assert result is True
        assert (templates_dir / "saveme.txt").exists()


class TestDefaultPromptManager:
    def test_is_initialized(self):
        assert default_prompt_manager is not None
        assert len(default_prompt_manager.templates) == 10

    def test_entity_extraction_template_has_content_var(self):
        result = default_prompt_manager.format_prompt(
            "entity_extraction", content="some transcript"
        )
        assert "some transcript" in result

    def test_mermaid_generation_template(self):
        result = default_prompt_manager.format_prompt(
            "mermaid_generation",
            diagram_type="flowchart",
            text_content="A -> B",
            semantic_analysis="Flow diagram",
        )
        assert "flowchart" in result
        assert "A -> B" in result
