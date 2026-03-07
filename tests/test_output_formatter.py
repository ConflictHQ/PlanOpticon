"""Tests for video_processor.cli.output_formatter.OutputFormatter."""

from pathlib import Path

import pytest

from video_processor.cli.output_formatter import OutputFormatter


@pytest.fixture()
def tmp_dir(tmp_path):
    """Return a fresh temp directory that is cleaned up automatically."""
    return tmp_path


@pytest.fixture()
def formatter(tmp_dir):
    """Return an OutputFormatter pointed at a temp output directory."""
    return OutputFormatter(tmp_dir / "output")


# --- Constructor ---


def test_constructor_creates_output_dir(tmp_dir):
    out = tmp_dir / "new_output"
    assert not out.exists()
    OutputFormatter(out)
    assert out.is_dir()


def test_constructor_accepts_string(tmp_dir):
    fmt = OutputFormatter(str(tmp_dir / "str_output"))
    assert fmt.output_dir.is_dir()


# --- organize_outputs ---


def _create_file(path: Path, content: str = "test") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_organize_outputs_basic(formatter, tmp_dir):
    md = _create_file(tmp_dir / "analysis.md", "# Title")
    kg = _create_file(tmp_dir / "kg.json", "{}")

    result = formatter.organize_outputs(
        markdown_path=md,
        knowledge_graph_path=kg,
        diagrams=[],
    )

    assert "markdown" in result
    assert "knowledge_graph" in result
    assert Path(result["markdown"]).exists()
    assert Path(result["knowledge_graph"]).exists()
    assert result["diagram_images"] == []
    assert result["frames"] == []
    assert result["transcript"] is None


def test_organize_outputs_with_transcript(formatter, tmp_dir):
    md = _create_file(tmp_dir / "analysis.md")
    kg = _create_file(tmp_dir / "kg.json")
    transcript = _create_file(tmp_dir / "transcript.txt", "Hello world")

    result = formatter.organize_outputs(
        markdown_path=md,
        knowledge_graph_path=kg,
        diagrams=[],
        transcript_path=transcript,
    )

    assert result["transcript"] is not None
    assert Path(result["transcript"]).exists()


def test_organize_outputs_with_diagrams(formatter, tmp_dir):
    md = _create_file(tmp_dir / "analysis.md")
    kg = _create_file(tmp_dir / "kg.json")
    img = _create_file(tmp_dir / "diagram1.png", "fake-png")

    result = formatter.organize_outputs(
        markdown_path=md,
        knowledge_graph_path=kg,
        diagrams=[{"image_path": str(img)}],
    )

    assert len(result["diagram_images"]) == 1
    assert Path(result["diagram_images"][0]).exists()


def test_organize_outputs_skips_missing_diagram(formatter, tmp_dir):
    md = _create_file(tmp_dir / "analysis.md")
    kg = _create_file(tmp_dir / "kg.json")

    result = formatter.organize_outputs(
        markdown_path=md,
        knowledge_graph_path=kg,
        diagrams=[{"image_path": "/nonexistent/diagram.png"}],
    )

    assert result["diagram_images"] == []


def test_organize_outputs_diagram_without_image_path(formatter, tmp_dir):
    md = _create_file(tmp_dir / "analysis.md")
    kg = _create_file(tmp_dir / "kg.json")

    result = formatter.organize_outputs(
        markdown_path=md,
        knowledge_graph_path=kg,
        diagrams=[{"description": "A diagram"}],
    )

    assert result["diagram_images"] == []


def test_organize_outputs_with_frames(formatter, tmp_dir):
    md = _create_file(tmp_dir / "analysis.md")
    kg = _create_file(tmp_dir / "kg.json")
    frames_dir = tmp_dir / "frames"
    frames_dir.mkdir()
    for i in range(5):
        _create_file(frames_dir / f"frame_{i:03d}.jpg", f"frame{i}")

    result = formatter.organize_outputs(
        markdown_path=md,
        knowledge_graph_path=kg,
        diagrams=[],
        frames_dir=frames_dir,
    )

    assert len(result["frames"]) == 5


def test_organize_outputs_limits_frames_to_10(formatter, tmp_dir):
    md = _create_file(tmp_dir / "analysis.md")
    kg = _create_file(tmp_dir / "kg.json")
    frames_dir = tmp_dir / "frames"
    frames_dir.mkdir()
    for i in range(25):
        _create_file(frames_dir / f"frame_{i:03d}.jpg", f"frame{i}")

    result = formatter.organize_outputs(
        markdown_path=md,
        knowledge_graph_path=kg,
        diagrams=[],
        frames_dir=frames_dir,
    )

    assert len(result["frames"]) <= 10


def test_organize_outputs_missing_frames_dir(formatter, tmp_dir):
    md = _create_file(tmp_dir / "analysis.md")
    kg = _create_file(tmp_dir / "kg.json")

    result = formatter.organize_outputs(
        markdown_path=md,
        knowledge_graph_path=kg,
        diagrams=[],
        frames_dir=tmp_dir / "nonexistent_frames",
    )

    assert result["frames"] == []


# --- create_html_index ---


def test_create_html_index_returns_path(formatter, tmp_dir):
    outputs = {
        "markdown": str(formatter.output_dir / "markdown" / "analysis.md"),
        "knowledge_graph": str(formatter.output_dir / "data" / "kg.json"),
        "diagram_images": [],
        "frames": [],
        "transcript": None,
    }
    # Create the referenced files so relative_to works
    for key in ("markdown", "knowledge_graph"):
        _create_file(Path(outputs[key]))

    index = formatter.create_html_index(outputs)
    assert index.exists()
    assert index.name == "index.html"


def test_create_html_index_contains_analysis_link(formatter, tmp_dir):
    md_path = formatter.output_dir / "markdown" / "analysis.md"
    _create_file(md_path)
    outputs = {
        "markdown": str(md_path),
        "knowledge_graph": None,
        "diagram_images": [],
        "frames": [],
        "transcript": None,
    }

    index = formatter.create_html_index(outputs)
    content = index.read_text()
    assert "Analysis Report" in content
    assert "analysis.md" in content


def test_create_html_index_with_diagrams(formatter, tmp_dir):
    img_path = formatter.output_dir / "diagrams" / "d1.png"
    _create_file(img_path)
    outputs = {
        "markdown": None,
        "knowledge_graph": None,
        "diagram_images": [str(img_path)],
        "frames": [],
        "transcript": None,
    }

    index = formatter.create_html_index(outputs)
    content = index.read_text()
    assert "Diagrams" in content
    assert "d1.png" in content


def test_create_html_index_with_frames(formatter, tmp_dir):
    frame_path = formatter.output_dir / "frames" / "frame_001.jpg"
    _create_file(frame_path)
    outputs = {
        "markdown": None,
        "knowledge_graph": None,
        "diagram_images": [],
        "frames": [str(frame_path)],
        "transcript": None,
    }

    index = formatter.create_html_index(outputs)
    content = index.read_text()
    assert "Key Frames" in content
    assert "frame_001.jpg" in content


def test_create_html_index_with_data_files(formatter, tmp_dir):
    kg_path = formatter.output_dir / "data" / "kg.json"
    transcript_path = formatter.output_dir / "data" / "transcript.txt"
    _create_file(kg_path)
    _create_file(transcript_path)
    outputs = {
        "markdown": None,
        "knowledge_graph": str(kg_path),
        "diagram_images": [],
        "frames": [],
        "transcript": str(transcript_path),
    }

    index = formatter.create_html_index(outputs)
    content = index.read_text()
    assert "Data Files" in content
    assert "kg.json" in content
    assert "transcript.txt" in content


def test_create_html_index_empty_outputs(formatter):
    outputs = {
        "markdown": None,
        "knowledge_graph": None,
        "diagram_images": [],
        "frames": [],
        "transcript": None,
    }

    index = formatter.create_html_index(outputs)
    content = index.read_text()
    assert "PlanOpticon Analysis Results" in content
    assert "<!DOCTYPE html>" in content
