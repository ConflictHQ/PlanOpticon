"""Tests for PlanGenerator — markdown report and batch summary generation.

The LLM boundary (``ProviderManager.chat``) is the only mocked dependency; the
real templating, key-point/diagram rendering, and knowledge-graph mermaid
generation all run. Knowledge graphs are real (in-memory) stores and every file
is written under ``tmp_path``.
"""

from unittest.mock import MagicMock

from video_processor.integrators.knowledge_graph import KnowledgeGraph
from video_processor.integrators.plan_generator import PlanGenerator
from video_processor.models import (
    ActionItem,
    DiagramResult,
    KeyPoint,
    VideoManifest,
    VideoMetadata,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pm(chat="Generated text."):
    pm = MagicMock()
    pm.chat.return_value = chat
    return pm


def _kg_with_nodes():
    """A real KnowledgeGraph (in-memory) with two linked technology entities."""
    return KnowledgeGraph.from_dict(
        {
            "nodes": [
                {"name": "Python", "type": "technology", "descriptions": ["language"]},
                {"name": "Django", "type": "technology", "descriptions": ["framework"]},
            ],
            "relationships": [
                {"source": "Django", "target": "Python", "type": "uses"},
            ],
        }
    )


def _make_manifest(title, *, key_points=None, action_items=None, diagrams=None, duration=None):
    return VideoManifest(
        video=VideoMetadata(title=title, duration_seconds=duration),
        key_points=key_points or [],
        action_items=action_items or [],
        diagrams=diagrams or [],
    )


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_creates_default_knowledge_graph(self):
        gen = PlanGenerator(provider_manager=_make_pm())
        assert isinstance(gen.knowledge_graph, KnowledgeGraph)

    def test_uses_provided_knowledge_graph(self):
        kg = KnowledgeGraph(provider_manager=None)
        gen = PlanGenerator(provider_manager=_make_pm(), knowledge_graph=kg)
        assert gen.knowledge_graph is kg


# ---------------------------------------------------------------------------
# generate_summary
# ---------------------------------------------------------------------------


class TestGenerateSummary:
    def test_summary_from_segments_includes_speakers(self):
        pm = _make_pm(chat="A three paragraph summary.")
        gen = PlanGenerator(provider_manager=pm)
        transcript = {
            "segments": [
                {"speaker": "Alice", "text": "We should ship the auth service first."},
                {"speaker": "Bob", "text": "Agreed, but mind the deadline."},
            ]
        }

        summary = gen.generate_summary(transcript)

        assert summary == "A three paragraph summary."
        prompt = pm.chat.call_args[0][0][0]["content"]
        assert "Alice: We should ship the auth service first." in prompt
        assert "Bob: Agreed, but mind the deadline." in prompt

    def test_summary_falls_back_to_plain_text(self):
        pm = _make_pm(chat="Summary.")
        gen = PlanGenerator(provider_manager=pm)

        summary = gen.generate_summary({"text": "a plain transcript without segments"})

        assert summary == "Summary."
        prompt = pm.chat.call_args[0][0][0]["content"]
        assert "a plain transcript without segments" in prompt

    def test_summary_without_provider_returns_empty(self):
        gen = PlanGenerator(provider_manager=None)
        assert gen.generate_summary({"text": "anything"}) == ""


# ---------------------------------------------------------------------------
# generate_markdown
# ---------------------------------------------------------------------------


class TestGenerateMarkdown:
    def test_full_report_renders_all_sections(self):
        pm = _make_pm(chat="The overall summary.")
        gen = PlanGenerator(provider_manager=pm)
        key_points = [{"point": "Adopt CI", "details": ["run tests", "gate merges"]}]
        diagrams = [
            {
                "description": "System architecture overview",
                "image_path": "diagrams/diagram_0.jpg",
                "mermaid": "graph LR\n  A --> B",
            }
        ]
        knowledge_graph = {
            "nodes": [
                {"name": "Python", "type": "technology", "descriptions": ["language"]},
                {"name": "Django", "type": "technology", "descriptions": ["framework"]},
            ],
            "relationships": [{"source": "Django", "target": "Python", "type": "uses"}],
        }

        md = gen.generate_markdown(
            transcript={"text": "the transcript"},
            key_points=key_points,
            diagrams=diagrams,
            knowledge_graph=knowledge_graph,
            video_title="Design Review",
        )

        assert md.startswith("# Design Review")
        assert "## Summary" in md
        assert "The overall summary." in md
        assert "## Key Points" in md
        assert "- **Adopt CI**" in md
        assert "  - run tests" in md
        assert "## Visual Elements" in md
        assert "### Diagram 1" in md
        assert "System architecture overview" in md
        assert "![Diagram 1](diagrams/diagram_0.jpg)" in md
        assert "```mermaid" in md
        assert "## Knowledge Graph" in md
        # KG mermaid is rendered from the reconstructed graph.
        assert "graph LR" in md

    def test_details_as_string_renders_indented(self):
        gen = PlanGenerator(provider_manager=_make_pm())
        md = gen.generate_markdown(
            transcript={"text": "t"},
            key_points=[{"point": "One point", "details": "a single detail line"}],
            diagrams=[],
            knowledge_graph={},
        )
        assert "- **One point**" in md
        assert "  a single detail line" in md

    def test_string_key_point_uses_str(self):
        gen = PlanGenerator(provider_manager=_make_pm())
        md = gen.generate_markdown(
            transcript={"text": "t"},
            key_points=["just a raw string point"],
            diagrams=[],
            knowledge_graph={},
        )
        assert "- **just a raw string point**" in md

    def test_minimal_report_omits_optional_sections(self):
        gen = PlanGenerator(provider_manager=_make_pm(chat="s"))
        md = gen.generate_markdown(
            transcript={"text": "t"},
            key_points=[],
            diagrams=[],
            knowledge_graph={"nodes": []},
            video_title=None,
        )
        assert "# Video Analysis Report" in md  # default title
        assert "## Visual Elements" not in md
        assert "## Knowledge Graph" not in md

    def test_writes_file_and_appends_md_suffix(self, tmp_path):
        gen = PlanGenerator(provider_manager=_make_pm(chat="written summary"))
        out = tmp_path / "reports" / "analysis"  # no suffix

        md = gen.generate_markdown(
            transcript={"text": "t"},
            key_points=[],
            diagrams=[],
            knowledge_graph={},
            output_path=out,
        )

        written = tmp_path / "reports" / "analysis.md"
        assert written.exists()
        assert written.read_text() == md
        assert "written summary" in md


# ---------------------------------------------------------------------------
# generate_batch_summary
# ---------------------------------------------------------------------------


class TestGenerateBatchSummary:
    def test_overview_and_per_video_sections(self):
        gen = PlanGenerator(provider_manager=_make_pm())
        manifests = [
            _make_manifest(
                "Kickoff",
                key_points=[KeyPoint(point="Scope agreed")],
                action_items=[
                    ActionItem(action="Email report", assignee="Alice", deadline="Friday")
                ],
                diagrams=[DiagramResult(frame_index=0)],
                duration=120.0,
            ),
            _make_manifest(
                "Retro",
                key_points=[KeyPoint(point="Ship faster"), KeyPoint(point="Fewer meetings")],
            ),
        ]

        md = gen.generate_batch_summary(manifests, title="Sprint Batch")

        assert md.startswith("# Sprint Batch")
        assert "- **Videos processed:** 2" in md
        assert "- **Total diagrams:** 1" in md
        assert "- **Total key points:** 3" in md
        assert "- **Total action items:** 1" in md
        # Per-video sections and duration line.
        assert "### Kickoff" in md
        assert "### Retro" in md
        assert "- Duration: 120s" in md
        # Aggregated action items carry assignee, deadline and source video title.
        assert "## All Action Items" in md
        assert "- **Email report** (Alice) — Friday _Kickoff_" in md

    def test_no_action_items_omits_section(self):
        gen = PlanGenerator(provider_manager=_make_pm())
        manifests = [_make_manifest("A", key_points=[KeyPoint(point="p")])]
        md = gen.generate_batch_summary(manifests)
        assert "## All Action Items" not in md

    def test_merged_knowledge_graph_section(self):
        gen = PlanGenerator(provider_manager=_make_pm())
        manifests = [_make_manifest("A")]
        md = gen.generate_batch_summary(manifests, kg=_kg_with_nodes())
        assert "## Merged Knowledge Graph" in md
        assert "graph LR" in md
        assert "Python" in md

    def test_without_knowledge_graph_omits_section(self):
        gen = PlanGenerator(provider_manager=_make_pm())
        md = gen.generate_batch_summary([_make_manifest("A")], kg=None)
        assert "## Merged Knowledge Graph" not in md

    def test_writes_file(self, tmp_path):
        gen = PlanGenerator(provider_manager=_make_pm())
        out = tmp_path / "batch" / "summary.md"
        md = gen.generate_batch_summary([_make_manifest("Only")], output_path=out)
        assert out.exists()
        assert out.read_text() == md
        assert "### Only" in out.read_text()
