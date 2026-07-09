"""Tests for the agentic orchestrator's execution, retry, and reporting logic.

These exercise the parts of ``AgentOrchestrator`` not already covered by
``tests/test_agent.py`` (which covers ``_create_plan``, ``_adapt_plan``,
``_get_fallback``, ``_deep_analysis``, ``_build_manifest`` and ``insights``):
the ``_run_step`` dispatcher, ``_execute_step`` retry/fallback handling,
``_cross_reference``, ``_generate_reports`` and the top-level ``process`` flow.

The LLM boundary is the only thing mocked — a ``MagicMock`` ProviderManager is
passed in so the real orchestration, parsing, knowledge-graph and reporting code
runs. The knowledge graph is a real SQLite/in-memory store and all files land in
``tmp_path``.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from video_processor.agent.orchestrator import AgentOrchestrator
from video_processor.integrators.knowledge_graph import KnowledgeGraph
from video_processor.models import ActionItem, DiagramResult, KeyPoint, VideoManifest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pm(chat="[]", analyze_image="{}", transcribe=None):
    """Build a mock ProviderManager with representative return values.

    Only the LLM boundary is mocked; callers override ``chat`` /
    ``transcribe_audio`` per test to drive the real parsing branches.
    """
    pm = MagicMock()
    pm.chat.return_value = chat
    pm.analyze_image.return_value = analyze_image
    pm.transcribe_audio.return_value = (
        transcribe if transcribe is not None else {"text": "", "segments": []}
    )
    pm.get_models_used.return_value = {"chat": "mock-chat", "vision": "mock-vision"}
    return pm


# ---------------------------------------------------------------------------
# _run_step — per-step dispatch
# ---------------------------------------------------------------------------


class TestRunStep:
    def test_transcribe_writes_transcript_files(self, tmp_path):
        pm = _make_pm()
        pm.transcribe_audio.return_value = {
            "text": "hello world",
            "segments": [{"start": 0.0, "end": 1.0, "text": "hello world"}],
        }
        agent = AgentOrchestrator(provider_manager=pm)
        agent._results["extract_audio"] = {"audio_path": "/audio/talk.wav"}

        result = agent._run_step("transcribe", Path("talk.mp4"), tmp_path)

        assert result["text"] == "hello world"
        pm.transcribe_audio.assert_called_once_with("/audio/talk.wav")
        tj = tmp_path / "transcript" / "transcript.json"
        tt = tmp_path / "transcript" / "transcript.txt"
        assert tt.read_text() == "hello world"
        assert json.loads(tj.read_text())["text"] == "hello world"

    def test_transcribe_without_audio_raises(self, tmp_path):
        agent = AgentOrchestrator(provider_manager=_make_pm())
        # No extract_audio result recorded → transcription has no input.
        with pytest.raises(RuntimeError, match="No audio available"):
            agent._run_step("transcribe", Path("talk.mp4"), tmp_path)

    def test_detect_diagrams_no_frames_returns_empty(self, tmp_path):
        agent = AgentOrchestrator(provider_manager=_make_pm())
        agent._results["extract_frames"] = {"paths": []}
        result = agent._run_step("detect_diagrams", Path("talk.mp4"), tmp_path)
        assert result == {"diagrams": [], "captures": []}

    def test_extract_key_points_parses_llm_json(self, tmp_path):
        pm = _make_pm(
            chat=json.dumps(
                [
                    {"point": "Adopt microservices", "topic": "arch", "details": "split monolith"},
                    {"point": "Ship by Q3", "topic": "timeline"},
                ]
            )
        )
        agent = AgentOrchestrator(provider_manager=pm)
        agent._results["transcribe"] = {"text": "a long enough transcript to analyze"}

        result = agent._run_step("extract_key_points", Path("talk.mp4"), tmp_path)

        kps = result["key_points"]
        assert [kp.point for kp in kps] == ["Adopt microservices", "Ship by Q3"]
        assert isinstance(kps[0], KeyPoint)

    def test_extract_key_points_empty_transcript_skips_llm(self, tmp_path):
        pm = _make_pm()
        agent = AgentOrchestrator(provider_manager=pm)
        agent._results["transcribe"] = {"text": ""}
        result = agent._run_step("extract_key_points", Path("talk.mp4"), tmp_path)
        assert result == {"key_points": []}
        pm.chat.assert_not_called()

    def test_extract_action_items_parses_llm_json(self, tmp_path):
        pm = _make_pm(
            chat=json.dumps(
                [{"action": "Email the report", "assignee": "Alice", "deadline": "Friday"}]
            )
        )
        agent = AgentOrchestrator(provider_manager=pm)
        agent._results["transcribe"] = {"text": "please email the report to the team"}

        result = agent._run_step("extract_action_items", Path("talk.mp4"), tmp_path)

        items = result["action_items"]
        assert len(items) == 1
        assert items[0].action == "Email the report"
        assert items[0].assignee == "Alice"

    def test_extract_action_items_empty_transcript_skips_llm(self, tmp_path):
        pm = _make_pm()
        agent = AgentOrchestrator(provider_manager=pm)
        agent._results["transcribe"] = {"text": ""}
        result = agent._run_step("extract_action_items", Path("talk.mp4"), tmp_path)
        assert result == {"action_items": []}
        pm.chat.assert_not_called()

    def test_build_knowledge_graph_persists_real_graph(self, tmp_path):
        pm = _make_pm(
            chat=json.dumps(
                {
                    "entities": [
                        {"name": "Alice", "type": "person", "description": "the lead"},
                        {"name": "Python", "type": "technology", "description": "language"},
                    ],
                    "relationships": [
                        {"source": "Alice", "target": "Python", "type": "uses"},
                    ],
                }
            )
        )
        agent = AgentOrchestrator(provider_manager=pm)
        agent._results["transcribe"] = {
            "segments": [{"start": 0.0, "end": 5.0, "text": "Alice uses Python every day"}],
        }
        # A detected diagram with text is folded into the same graph.
        agent._results["detect_diagrams"] = {
            "diagrams": [
                DiagramResult(
                    frame_index=1,
                    description="architecture",
                    text_content="Django is a Python web framework",
                )
            ]
        }

        result = agent._run_step("build_knowledge_graph", Path("talk.mp4"), tmp_path)

        kg = result["knowledge_graph"]
        assert isinstance(kg, KnowledgeGraph)
        assert "Python" in kg.nodes
        assert "Alice" in kg.nodes
        assert len(kg.relationships) >= 1
        # process_diagrams added a diagram entity from the detected diagram.
        assert "diagram_0" in kg.nodes
        # Both the SQLite db and its JSON export are written alongside each other.
        assert (tmp_path / "results" / "knowledge_graph.db").exists()
        assert (tmp_path / "results" / "knowledge_graph.json").exists()

    def test_deep_analysis_dispatch_surfaces_insights(self, tmp_path):
        pm = _make_pm(
            chat=json.dumps(
                {
                    "decisions": ["Use Postgres"],
                    "risks": ["Tight deadline"],
                    "follow_ups": [],
                    "tensions": [],
                }
            )
        )
        agent = AgentOrchestrator(provider_manager=pm)
        agent._results["transcribe"] = {"text": "a transcript worth analyzing in depth"}

        result = agent._run_step("deep_analysis", Path("talk.mp4"), tmp_path)

        assert result["decisions"] == ["Use Postgres"]
        assert any("Postgres" in i for i in agent.insights)
        assert any("Tight deadline" in i for i in agent.insights)

    def test_screengrab_fallback_returns_empty(self, tmp_path):
        agent = AgentOrchestrator(provider_manager=_make_pm())
        assert agent._run_step("screengrab_fallback", Path("talk.mp4"), tmp_path) == {}

    def test_unknown_step_raises(self, tmp_path):
        agent = AgentOrchestrator(provider_manager=_make_pm())
        with pytest.raises(ValueError, match="Unknown step"):
            agent._run_step("not_a_real_step", Path("talk.mp4"), tmp_path)


# ---------------------------------------------------------------------------
# _execute_step — retry and fallback handling
# ---------------------------------------------------------------------------


class TestExecuteStep:
    def test_retries_then_succeeds(self, tmp_path):
        pm = _make_pm()
        # First attempt raises, second succeeds — proves the retry loop re-runs.
        pm.transcribe_audio.side_effect = [
            RuntimeError("transient network error"),
            {"text": "recovered", "segments": []},
        ]
        agent = AgentOrchestrator(provider_manager=pm, max_retries=2)
        agent._results["extract_audio"] = {"audio_path": "/audio/talk.wav"}

        agent._execute_step(
            {"step": "transcribe", "priority": "required"}, Path("talk.mp4"), tmp_path
        )

        assert pm.transcribe_audio.call_count == 2
        assert agent._results["transcribe"] == {"text": "recovered", "segments": []}

    def test_retries_exhausted_records_error(self, tmp_path):
        pm = _make_pm()
        pm.transcribe_audio.side_effect = RuntimeError("permanent failure")
        agent = AgentOrchestrator(provider_manager=pm, max_retries=2)
        agent._results["extract_audio"] = {"audio_path": "/audio/talk.wav"}

        agent._execute_step(
            {"step": "transcribe", "priority": "required"}, Path("talk.mp4"), tmp_path
        )

        # Attempted exactly max_retries times, then the error was recorded.
        assert pm.transcribe_audio.call_count == 2
        assert agent._results["transcribe"] == {"error": "permanent failure"}

    def test_falls_back_after_exhausted_retries(self, tmp_path):
        # detect_diagrams is the only step with a fallback (screengrab_fallback).
        # A frame path that doesn't exist makes DiagramAnalyzer.process_frames raise
        # (the content hash opens the file), so every attempt fails and the
        # orchestrator switches to the fallback, which returns {}.
        agent = AgentOrchestrator(provider_manager=_make_pm(), max_retries=2)
        agent._results["extract_frames"] = {"paths": [str(tmp_path / "no_such_frame.jpg")]}

        agent._execute_step(
            {"step": "detect_diagrams", "priority": "standard"}, Path("talk.mp4"), tmp_path
        )

        # Error would remain if the fallback hadn't run; {} proves the fallback executed.
        assert agent._results["detect_diagrams"] == {}

    def test_successful_step_triggers_adaptive_planning(self, tmp_path):
        # A long transcript should cause _adapt_plan (invoked from _execute_step on
        # success) to append a deep_analysis step.
        pm = _make_pm()
        pm.transcribe_audio.return_value = {"text": "word " * 3000, "segments": []}
        agent = AgentOrchestrator(provider_manager=pm)
        agent._results["extract_audio"] = {"audio_path": "/audio/talk.wav"}
        agent._plan = [{"step": "generate_reports", "priority": "required"}]

        agent._execute_step(
            {"step": "transcribe", "priority": "required"}, Path("talk.mp4"), tmp_path
        )

        assert any(s["step"] == "deep_analysis" for s in agent._plan)


# ---------------------------------------------------------------------------
# _cross_reference
# ---------------------------------------------------------------------------


class TestCrossReference:
    def test_enriches_key_points_with_diagram_links(self, tmp_path):
        agent = AgentOrchestrator(provider_manager=_make_pm())
        agent._results["transcribe"] = {"text": "authentication service design discussion"}
        agent._results["build_knowledge_graph"] = {
            "knowledge_graph": KnowledgeGraph(provider_manager=None)
        }
        kp = KeyPoint(point="authentication service", details="oauth design")
        agent._results["extract_key_points"] = {"key_points": [kp]}
        diagram = DiagramResult(
            frame_index=0,
            elements=["authentication", "service"],
            text_content="design oauth flow",
        )
        agent._results["detect_diagrams"] = {"diagrams": [diagram]}

        # Route through _run_step to also cover the dispatch branch.
        result = agent._run_step("cross_reference", Path("talk.mp4"), tmp_path)

        assert result == {"enriched": True}
        # The key point now links to diagram index 0 (>=2 shared tokens).
        enriched = agent._results["extract_key_points"]["key_points"][0]
        assert enriched.related_diagrams == [0]

    def test_no_knowledge_graph_returns_empty(self, tmp_path):
        agent = AgentOrchestrator(provider_manager=_make_pm())
        # No build_knowledge_graph result → nothing to cross-reference.
        assert agent._cross_reference() == {}


# ---------------------------------------------------------------------------
# _generate_reports
# ---------------------------------------------------------------------------


class TestGenerateReports:
    def test_writes_markdown_with_summary_and_insights(self, tmp_path):
        pm = _make_pm(chat="This is the generated summary.")
        agent = AgentOrchestrator(provider_manager=pm)
        agent._results["transcribe"] = {"text": "the meeting transcript"}
        agent._results["extract_key_points"] = {
            "key_points": [KeyPoint(point="Key decision made", details="the details")]
        }
        agent._results["detect_diagrams"] = {"diagrams": []}
        agent._insights = ["Consider re-processing at comprehensive depth"]

        result = agent._run_step("generate_reports", Path("talk.mp4"), tmp_path)

        md_path = Path(result["report_path"])
        assert md_path.name == "analysis.md"
        assert md_path.exists()
        content = md_path.read_text()
        assert "This is the generated summary." in content
        assert "Key decision made" in content
        # Agent insights are appended to the report.
        assert "## Agent Insights" in content
        assert "Consider re-processing at comprehensive depth" in content


# ---------------------------------------------------------------------------
# _reflect_and_enrich — Phase 3 consolidation pass
#
# Reflection runs one LLM pass over a compact summary of the executed steps and
# merges consolidated insight strings into self._insights (deduped). It is
# best-effort: any LLM/parse failure is swallowed so process() can still build
# the manifest with the insights already accumulated during execution.
# ---------------------------------------------------------------------------


class TestReflectAndEnrich:
    def test_merges_and_dedupes_new_insights(self, tmp_path):
        # The reflection response mixes a duplicate of an existing insight, an
        # empty string and a non-string entry among two genuinely new insights.
        pm = _make_pm(
            chat=json.dumps(
                [
                    "Theme: the team keeps circling back to onboarding",
                    "",  # empty → skipped
                    42,  # non-string → skipped
                    "Existing insight",  # duplicate → deduped
                    "Risk: the Q3 deadline has no owner",
                ]
            )
        )
        agent = AgentOrchestrator(provider_manager=pm)
        agent._insights = ["Existing insight"]
        agent._results["transcribe"] = {"text": "a transcript worth reflecting on"}
        agent._results["extract_key_points"] = {"key_points": [KeyPoint(point="Adopt SSO")]}
        agent._results["extract_action_items"] = {
            "action_items": [ActionItem(action="Assign a deadline owner")]
        }

        agent._reflect_and_enrich(tmp_path)

        pm.chat.assert_called_once()
        # Duplicate/empty/non-string dropped; the two new insights appended in order.
        assert agent.insights == [
            "Existing insight",
            "Theme: the team keeps circling back to onboarding",
            "Risk: the Q3 deadline has no owner",
        ]

    def test_summary_covers_key_points_and_action_items(self, tmp_path):
        # The compact summary the LLM reflects over includes the extracted point
        # and action text, so reflection reasons over real step output.
        pm = _make_pm(chat="[]")
        agent = AgentOrchestrator(provider_manager=pm)
        agent._results["transcribe"] = {"text": "transcript body"}
        agent._results["extract_key_points"] = {"key_points": [KeyPoint(point="Adopt SSO")]}
        agent._results["extract_action_items"] = {
            "action_items": [ActionItem(action="Email the runbook")]
        }

        agent._reflect_and_enrich(tmp_path)

        prompt = pm.chat.call_args.args[0][0]["content"]
        assert "Adopt SSO" in prompt
        assert "Email the runbook" in prompt
        assert "transcript body" in prompt

    def test_chat_error_preserves_insights(self, tmp_path):
        # An LLM failure during reflection must not raise or lose prior insights.
        pm = _make_pm()
        pm.chat.side_effect = RuntimeError("provider exploded")
        agent = AgentOrchestrator(provider_manager=pm)
        agent._insights = ["Pre-reflection insight"]
        agent._results["transcribe"] = {"text": "a transcript worth reflecting on"}

        agent._reflect_and_enrich(tmp_path)  # no exception propagates

        assert agent.insights == ["Pre-reflection insight"]

    def test_malformed_json_preserves_insights(self, tmp_path):
        # A response that is not JSON parses to None → nothing merged, no crash.
        pm = _make_pm(chat="Sorry, I could not produce structured output.")
        agent = AgentOrchestrator(provider_manager=pm)
        agent._insights = ["Pre-reflection insight"]
        agent._results["transcribe"] = {"text": "a transcript worth reflecting on"}

        agent._reflect_and_enrich(tmp_path)

        assert agent.insights == ["Pre-reflection insight"]

    def test_skips_llm_when_nothing_extracted(self, tmp_path):
        # No transcript / points / items / prior insights → no reason to reflect,
        # so the LLM is not called at all.
        pm = _make_pm()
        agent = AgentOrchestrator(provider_manager=pm)

        agent._reflect_and_enrich(tmp_path)

        pm.chat.assert_not_called()
        assert agent.insights == []


# ---------------------------------------------------------------------------
# process — end-to-end drive
#
# process() runs plan → execute → reflect → manifest and returns a
# VideoManifest. With a missing video the extraction steps degrade gracefully
# (their errors are recorded), the downstream steps run against empty input, and
# reflection is skipped (nothing was extracted). The dedicated reflection cases
# below seed insights so Phase 3 actually runs inside a full process() call.
# ---------------------------------------------------------------------------


def _reflection_chat(reflection_response):
    """side_effect that answers the reflection prompt distinctly from the rest.

    Every other chat call (e.g. report-summary generation) returns a short
    string; the reflection call is matched on its stable prompt preamble.
    ``reflection_response`` may be a value to return or an exception to raise.
    """

    def _chat(messages, *args, **kwargs):
        content = messages[0]["content"] if messages else ""
        if "reflecting on the results" in content:
            if isinstance(reflection_response, Exception):
                raise reflection_response
            return reflection_response
        return "A concise summary."

    return _chat


class TestProcess:
    def test_returns_manifest_with_basic_plan(self, tmp_path):
        pm = _make_pm(chat="A concise summary.")
        agent = AgentOrchestrator(provider_manager=pm, max_retries=1)
        video = tmp_path / "missing.mp4"  # does not exist → extraction steps fail
        out = tmp_path / "out"

        manifest = agent.process(video, out, initial_depth="basic")

        # Phase 4: process() now completes and returns a manifest.
        assert isinstance(manifest, VideoManifest)
        assert manifest.video.source_path == str(video)
        assert manifest.stats.duration_seconds >= 0

        # Phase 1: the basic plan was created in the expected order.
        assert [s["step"] for s in agent._plan] == [
            "extract_frames",
            "extract_audio",
            "transcribe",
            "extract_key_points",
            "extract_action_items",
            "generate_reports",
        ]

        # Phase 2: steps needing the (missing) video failed gracefully and the
        # error was recorded rather than aborting the run.
        assert "error" in agent._results["extract_frames"]
        assert "error" in agent._results["extract_audio"]
        assert "error" in agent._results["transcribe"]

        # Downstream steps still executed; report generation produced a file.
        assert agent._results["extract_key_points"] == {"key_points": []}
        assert agent._results["extract_action_items"] == {"action_items": []}
        assert "report_path" in agent._results["generate_reports"]
        assert (out / "results" / "analysis.md").exists()

    def test_comprehensive_depth_drives_extra_steps(self, tmp_path):
        # Comprehensive depth adds detect_diagrams, build_knowledge_graph,
        # deep_analysis and cross_reference to the plan. With no real video these
        # run against empty upstream results, exercising each step's empty-input
        # branch before process() reflects (a no-op here) and builds the manifest.
        pm = _make_pm(chat="A summary.")
        agent = AgentOrchestrator(provider_manager=pm, max_retries=1)
        video = tmp_path / "missing.mp4"
        out = tmp_path / "out"

        manifest = agent.process(video, out, initial_depth="comprehensive")

        assert isinstance(manifest, VideoManifest)
        assert [s["step"] for s in agent._plan] == [
            "extract_frames",
            "extract_audio",
            "transcribe",
            "detect_diagrams",
            "build_knowledge_graph",
            "extract_key_points",
            "extract_action_items",
            "deep_analysis",
            "cross_reference",
            "generate_reports",
        ]
        # detect_diagrams degrades to empty when frames are unavailable.
        assert agent._results["detect_diagrams"] == {"diagrams": [], "captures": []}
        # A knowledge graph object is still constructed (empty transcript).
        kg = agent._results["build_knowledge_graph"]["knowledge_graph"]
        assert isinstance(kg, KnowledgeGraph)
        # deep_analysis on empty text returns nothing; cross_reference still runs.
        assert agent._results["deep_analysis"] == {}
        assert agent._results["cross_reference"] == {"enriched": True}

    def test_process_surfaces_reflection_insights(self, tmp_path):
        # A seeded insight makes Phase 3 run inside process(); the reflection
        # response's insights are surfaced through agent.insights on the returned run.
        pm = _make_pm()
        pm.chat.side_effect = _reflection_chat(
            json.dumps(["Reflected: the timeline needs an owner"])
        )
        agent = AgentOrchestrator(provider_manager=pm, max_retries=1)
        agent._insights = ["Seed insight from execution"]
        out = tmp_path / "out"

        manifest = agent.process(tmp_path / "missing.mp4", out, initial_depth="basic")

        assert isinstance(manifest, VideoManifest)
        assert "Reflected: the timeline needs an owner" in agent.insights
        assert "Seed insight from execution" in agent.insights

    def test_process_completes_when_reflection_fails(self, tmp_path):
        # Reflection raising must not break the run: process() still returns a
        # manifest and the pre-reflection insights are left intact.
        pm = _make_pm()
        pm.chat.side_effect = _reflection_chat(RuntimeError("reflection provider down"))
        agent = AgentOrchestrator(provider_manager=pm, max_retries=1)
        agent._insights = ["Seed insight from execution"]
        out = tmp_path / "out"

        manifest = agent.process(tmp_path / "missing.mp4", out, initial_depth="basic")

        assert isinstance(manifest, VideoManifest)
        assert agent.insights == ["Seed insight from execution"]
