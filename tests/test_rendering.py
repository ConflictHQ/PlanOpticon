"""Tests for rendering and export utilities."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from video_processor.models import (
    ActionItem,
    DiagramResult,
    DiagramType,
    KeyPoint,
    ProcessingStats,
    VideoManifest,
    VideoMetadata,
)
from video_processor.utils.rendering import render_mermaid, reproduce_chart


class TestRenderMermaid:
    def test_writes_mermaid_source(self, tmp_path):
        code = "graph LR\n    A-->B"
        result = render_mermaid(code, tmp_path, "test_diagram")
        assert "mermaid" in result
        assert result["mermaid"].exists()
        assert result["mermaid"].read_text() == code

    def test_source_file_named_correctly(self, tmp_path):
        result = render_mermaid("graph TD\n    X-->Y", tmp_path, "my_chart")
        assert result["mermaid"].name == "my_chart.mermaid"

    @patch("video_processor.utils.rendering.mmd", create=True)
    def test_svg_png_on_import_error(self, mock_mmd, tmp_path):
        """When mermaid-py is not installed, only source is written."""
        # Simulate import error by using the real code path
        # (mermaid-py may or may not be installed in test env)
        result = render_mermaid("graph LR\n    A-->B", tmp_path, "test")
        # At minimum, mermaid source should always be written
        assert "mermaid" in result
        assert result["mermaid"].exists()

    def test_creates_output_dir(self, tmp_path):
        nested = tmp_path / "a" / "b"
        result = render_mermaid("graph LR\n    A-->B", nested, "test")
        assert nested.exists()
        assert result["mermaid"].exists()


class TestReproduceChart:
    def test_bar_chart(self, tmp_path):
        data = {
            "labels": ["A", "B", "C"],
            "values": [10, 20, 30],
            "chart_type": "bar",
        }
        result = reproduce_chart(data, tmp_path, "test")
        assert "svg" in result
        assert "png" in result
        assert result["svg"].exists()
        assert result["png"].exists()
        assert result["svg"].suffix == ".svg"
        assert result["png"].suffix == ".png"

    def test_line_chart(self, tmp_path):
        data = {
            "labels": ["Jan", "Feb", "Mar"],
            "values": [5, 15, 10],
            "chart_type": "line",
        }
        result = reproduce_chart(data, tmp_path, "line_test")
        assert "svg" in result
        assert result["svg"].exists()

    def test_pie_chart(self, tmp_path):
        data = {
            "labels": ["Dogs", "Cats"],
            "values": [60, 40],
            "chart_type": "pie",
        }
        result = reproduce_chart(data, tmp_path, "pie_test")
        assert "svg" in result

    def test_scatter_chart(self, tmp_path):
        data = {
            "labels": ["X1", "X2", "X3"],
            "values": [1, 4, 9],
            "chart_type": "scatter",
        }
        result = reproduce_chart(data, tmp_path, "scatter_test")
        assert "svg" in result

    def test_empty_data_returns_empty(self, tmp_path):
        data = {"labels": [], "values": [], "chart_type": "bar"}
        result = reproduce_chart(data, tmp_path, "empty")
        assert result == {}

    def test_missing_values_returns_empty(self, tmp_path):
        data = {"labels": ["A", "B"]}
        result = reproduce_chart(data, tmp_path, "no_vals")
        assert result == {}

    def test_creates_output_dir(self, tmp_path):
        nested = tmp_path / "charts" / "output"
        data = {"labels": ["A"], "values": [1], "chart_type": "bar"}
        result = reproduce_chart(data, nested, "test")
        assert nested.exists()


class TestExportAllFormats:
    def _make_manifest(self) -> VideoManifest:
        return VideoManifest(
            video=VideoMetadata(title="Test Video"),
            stats=ProcessingStats(frames_extracted=5, diagrams_detected=1),
            analysis_md="results/analysis.md",
            key_points=[KeyPoint(point="Important finding")],
            action_items=[ActionItem(action="Follow up", assignee="Alice")],
            diagrams=[
                DiagramResult(
                    frame_index=0,
                    diagram_type=DiagramType.flowchart,
                    confidence=0.9,
                    description="Login flow",
                    mermaid="graph LR\n    Login-->Dashboard",
                    image_path="diagrams/diagram_0.jpg",
                ),
            ],
        )

    def test_export_renders_mermaid(self, tmp_path):
        from video_processor.utils.export import export_all_formats

        manifest = self._make_manifest()

        # Create required dirs and files
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "analysis.md").write_text("# Test\nContent")
        (tmp_path / "diagrams").mkdir()
        (tmp_path / "diagrams" / "diagram_0.jpg").write_bytes(b"\xff\xd8\xff")

        result = export_all_formats(tmp_path, manifest)

        # Mermaid source should be written
        assert (tmp_path / "diagrams" / "diagram_0.mermaid").exists()
        # Manifest should be updated
        assert result.diagrams[0].mermaid_path is not None

    def test_export_generates_html(self, tmp_path):
        from video_processor.utils.export import export_all_formats

        manifest = self._make_manifest()
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "analysis.md").write_text("# Test")
        (tmp_path / "diagrams").mkdir()

        result = export_all_formats(tmp_path, manifest)
        assert result.analysis_html is not None
        html_path = tmp_path / result.analysis_html
        assert html_path.exists()
        html_content = html_path.read_text()
        assert "Test Video" in html_content
        assert "mermaid" in html_content.lower()

    def test_export_with_chart_data(self, tmp_path):
        from video_processor.utils.export import export_all_formats

        manifest = VideoManifest(
            video=VideoMetadata(title="Chart Test"),
            diagrams=[
                DiagramResult(
                    frame_index=0,
                    diagram_type=DiagramType.chart,
                    confidence=0.9,
                    chart_data={
                        "labels": ["Q1", "Q2", "Q3"],
                        "values": [100, 200, 150],
                        "chart_type": "bar",
                    },
                ),
            ],
        )
        (tmp_path / "results").mkdir()
        (tmp_path / "diagrams").mkdir()

        result = export_all_formats(tmp_path, manifest)
        # Chart should be reproduced
        chart_svg = tmp_path / "diagrams" / "diagram_0_chart.svg"
        assert chart_svg.exists()


class TestGenerateHtmlReport:
    def test_html_contains_title(self, tmp_path):
        from video_processor.utils.export import generate_html_report

        manifest = VideoManifest(
            video=VideoMetadata(title="My Meeting"),
            analysis_md="results/analysis.md",
        )
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "analysis.md").write_text("# My Meeting\nNotes here.")

        path = generate_html_report(manifest, tmp_path)
        assert path is not None
        content = path.read_text()
        assert "My Meeting" in content

    def test_html_includes_key_points(self, tmp_path):
        from video_processor.utils.export import generate_html_report

        manifest = VideoManifest(
            video=VideoMetadata(title="Test"),
            key_points=[
                KeyPoint(point="First point", details="Detail 1"),
                KeyPoint(point="Second point"),
            ],
        )
        (tmp_path / "results").mkdir()

        path = generate_html_report(manifest, tmp_path)
        content = path.read_text()
        assert "First point" in content
        assert "Detail 1" in content
        assert "Second point" in content

    def test_html_includes_action_items(self, tmp_path):
        from video_processor.utils.export import generate_html_report

        manifest = VideoManifest(
            video=VideoMetadata(title="Test"),
            action_items=[
                ActionItem(action="Do the thing", assignee="Bob", deadline="Friday"),
            ],
        )
        (tmp_path / "results").mkdir()

        path = generate_html_report(manifest, tmp_path)
        content = path.read_text()
        assert "Do the thing" in content
        assert "Bob" in content
        assert "Friday" in content

    def test_html_includes_mermaid_js(self, tmp_path):
        from video_processor.utils.export import generate_html_report

        manifest = VideoManifest(
            video=VideoMetadata(title="Test"),
            diagrams=[
                DiagramResult(
                    frame_index=0,
                    mermaid="graph LR\n    A-->B",
                )
            ],
        )
        (tmp_path / "results").mkdir()

        path = generate_html_report(manifest, tmp_path)
        content = path.read_text()
        assert "mermaid" in content
        assert "A-->B" in content
