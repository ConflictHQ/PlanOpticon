"""Branch coverage for CompanionREPL (complements test_companion.py + test_cli_ux.py).

Drives the REPL against a REAL SQLiteStore knowledge graph (never a mock DB) for
the KG-backed commands, exercises workspace discovery on real tmp files, and mocks
only true boundaries: the ProviderManager/LLM, the auth stack's HTTP, and readline.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from video_processor.agent.skills.base import Artifact
from video_processor.cli.companion import CompanionREPL
from video_processor.integrators.graph_store import SQLiteStore


def _make_graph_db(path: Path) -> Path:
    """Create a populated real SQLite knowledge graph at *path* and return it."""
    store = SQLiteStore(path)
    store.merge_entity("Python", "technology", ["A programming language"])
    store.merge_entity("Django", "technology", ["A web framework"])
    store.merge_entity("Alice", "person", ["Software engineer"])
    store.merge_entity("Bob", "person", ["Product manager"])
    store.merge_entity("Acme Corp", "organization", ["A tech company"])
    store.add_relationship("Alice", "Python", "uses")
    store.add_relationship("Alice", "Bob", "works_with")
    store.add_relationship("Django", "Python", "built_on")
    store.add_relationship("Alice", "Acme Corp", "employed_by")
    store.add_occurrence("Alice", "transcript_0", timestamp=1.0, text="Alice spoke")
    store.close()
    return path


def _repl_with_graph(tmp_path: Path) -> CompanionREPL:
    """Build a REPL with a real graph loaded (no LLM, no cwd scan)."""
    db = _make_graph_db(tmp_path / "knowledge_graph.db")
    repl = CompanionREPL(kb_paths=[str(db)])
    repl._kg_path = db
    repl._load_kg(db)
    return repl


def _close_kg(repl: CompanionREPL) -> None:
    """Close a real SQLite connection held open by a loaded REPL, if any."""
    if repl.kg is not None and hasattr(repl.kg, "close"):
        repl.kg.close()


@pytest.fixture
def graph_repl(tmp_path):
    """A REPL with a real SQLite graph loaded; connection closed on teardown."""
    repl = _repl_with_graph(tmp_path)
    yield repl
    _close_kg(repl)


# -----------------------------------------------------------------------
# Workspace discovery + KG loading
# -----------------------------------------------------------------------


class TestDiscovery:
    def test_discover_explicit_db_and_media(self, tmp_path, monkeypatch):
        db = _make_graph_db(tmp_path / "knowledge_graph.db")
        (tmp_path / "clip.mp4").write_bytes(b"fake video")
        (tmp_path / "notes.md").write_text("# notes")
        monkeypatch.chdir(tmp_path)

        repl = CompanionREPL(kb_paths=[str(db)])
        repl._discover()

        assert repl._kg_path == db
        assert repl.query_engine is not None
        assert repl.kg is not None
        assert any(p.name == "clip.mp4" for p in repl._videos)
        assert any(p.name == "notes.md" for p in repl._docs)
        _close_kg(repl)

    def test_discover_json_graph(self, tmp_path, monkeypatch):
        data = {
            "nodes": [
                {"name": "Python", "type": "technology", "descriptions": ["lang"]},
                {"name": "Alice", "type": "person", "descriptions": ["eng"]},
            ],
            "relationships": [{"source": "Alice", "target": "Python", "type": "uses"}],
        }
        jf = tmp_path / "knowledge_graph.json"
        jf.write_text(json.dumps(data))
        monkeypatch.chdir(tmp_path)

        repl = CompanionREPL(kb_paths=[str(jf)])
        repl._discover()

        assert repl.query_engine is not None
        assert repl.query_engine.stats().data["entity_count"] == 2

    def test_discover_swallows_permission_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        def _boom(self):
            raise PermissionError("denied")

        with (
            patch(
                "video_processor.integrators.graph_discovery.find_nearest_graph",
                return_value=None,
            ),
            patch.object(Path, "iterdir", _boom),
        ):
            repl = CompanionREPL()
            repl._discover()  # must not raise

        assert repl._videos == []
        assert repl._docs == []

    def test_load_kg_handles_bad_file(self, tmp_path):
        bad = tmp_path / "knowledge_graph.json"
        bad.write_text("not valid json {{{")
        repl = CompanionREPL(kb_paths=[str(bad)])
        repl._kg_path = bad
        repl._load_kg(bad)
        # Parse failure is swallowed; nothing gets loaded.
        assert repl.query_engine is None
        assert repl.kg is None


# -----------------------------------------------------------------------
# Welcome banner
# -----------------------------------------------------------------------


class TestWelcomeBanner:
    def test_banner_no_kg(self):
        banner = CompanionREPL()._welcome_banner()
        assert "PlanOpticon Companion" in banner
        assert "No knowledge graph loaded." in banner
        assert "LLM provider: none" in banner
        assert "/help" in banner

    def test_banner_with_kg(self, graph_repl):
        banner = graph_repl._welcome_banner()
        assert "Knowledge graph: knowledge_graph.db" in banner
        assert "5 entities" in banner
        assert "4 relationships" in banner

    def test_banner_truncates_videos_and_lists_docs(self):
        repl = CompanionREPL()
        repl._videos = [Path(f"v{i}.mp4") for i in range(5)]
        repl._docs = [Path("a.md"), Path("b.md")]
        banner = repl._welcome_banner()
        assert "Videos: v0.mp4, v1.mp4, v2.mp4 (+2 more)" in banner
        assert "Docs: a.md, b.md" in banner

    def test_banner_with_provider(self):
        repl = CompanionREPL(chat_model="gpt-4o")
        repl.provider_manager = MagicMock()
        repl.provider_manager.provider = "openai"
        banner = repl._welcome_banner()
        assert "LLM provider: openai (model: gpt-4o)" in banner


# -----------------------------------------------------------------------
# KG-backed slash commands (real graph engine)
# -----------------------------------------------------------------------


class TestStatusWithKG:
    def test_status_reports_counts_and_types(self, graph_repl):
        out = graph_repl.handle_input("/status")
        assert "KG:" in out
        assert "5 entities" in out
        assert "4 relationships" in out
        assert "technology: 2" in out
        assert "person: 2" in out


class TestEntitiesWithKG:
    def test_entities_all(self, graph_repl):
        out = graph_repl.handle_input("/entities")
        assert "Python" in out
        assert "Alice" in out

    def test_entities_filter_person(self, graph_repl):
        out = graph_repl.handle_input("/entities --type person")
        assert "Alice" in out
        assert "Bob" in out
        assert "Python" not in out

    def test_entities_filter_technology(self, graph_repl):
        out = graph_repl.handle_input("/entities --type technology")
        assert "Python" in out
        assert "Django" in out
        assert "Alice" not in out


class TestSearchWithKG:
    def test_search_match(self, graph_repl):
        out = graph_repl.handle_input("/search python")
        assert "Python" in out

    def test_search_empty_term(self, graph_repl):
        out = graph_repl.handle_input("/search")
        assert out == "Usage: /search TERM"

    def test_search_no_results(self, graph_repl):
        out = graph_repl.handle_input("/search zzznomatch")
        assert "No results found" in out


class TestNeighborsWithKG:
    def test_neighbors_match(self, graph_repl):
        out = graph_repl.handle_input("/neighbors Alice")
        assert "Alice" in out
        assert "Python" in out

    def test_neighbors_empty(self, graph_repl):
        out = graph_repl.handle_input("/neighbors")
        assert out == "Usage: /neighbors ENTITY"

    def test_neighbors_not_found(self, graph_repl):
        out = graph_repl.handle_input("/neighbors Ghost")
        assert "not found" in out


class TestExport:
    def test_export_empty(self):
        out = CompanionREPL().handle_input("/export")
        assert out.startswith("Usage: /export FORMAT")

    def test_export_no_kg(self):
        out = CompanionREPL().handle_input("/export markdown")
        assert out == "No knowledge graph loaded."

    def test_export_success(self, graph_repl):
        out = graph_repl.handle_input("/export markdown")
        assert "Export 'markdown' requested" in out
        assert "planopticon export markdown" in out


# -----------------------------------------------------------------------
# analyze / ingest (real filesystem checks)
# -----------------------------------------------------------------------


class TestAnalyzeIngest:
    def test_analyze_empty(self):
        assert CompanionREPL().handle_input("/analyze") == "Usage: /analyze PATH"

    def test_ingest_empty(self):
        assert CompanionREPL().handle_input("/ingest") == "Usage: /ingest PATH"

    def test_analyze_not_found(self):
        out = CompanionREPL().handle_input("/analyze /no/such/file.mp4")
        assert "File not found" in out

    def test_analyze_success(self, tmp_path):
        f = tmp_path / "vid.mp4"
        f.write_bytes(b"x")
        out = CompanionREPL().handle_input(f"/analyze {f}")
        assert "Analyze requested for vid.mp4" in out

    def test_ingest_not_found(self):
        out = CompanionREPL().handle_input("/ingest /no/such/doc.md")
        assert "File not found" in out

    def test_ingest_success(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("hello")
        out = CompanionREPL().handle_input(f"/ingest {f}")
        assert "Ingest requested for doc.md" in out


# -----------------------------------------------------------------------
# /run skill dispatch (skill registry mocked; DB never mocked)
# -----------------------------------------------------------------------


class TestRunSkill:
    def test_run_empty(self):
        assert CompanionREPL().handle_input("/run") == "Usage: /run SKILL_NAME"

    def test_unknown_skill(self):
        out = CompanionREPL().handle_input("/run definitely_not_a_skill_xyz")
        assert "Unknown skill" in out

    def test_plan_prd_tasks_dispatch_to_named_skills(self):
        # /plan, /prd, /tasks are shortcuts for specific skill names.
        with patch(
            "video_processor.agent.skills.base.get_skill",
            return_value=None,
        ):
            repl = CompanionREPL()
            assert repl.handle_input("/plan") == "Unknown skill: project_plan"
            assert repl.handle_input("/prd") == "Unknown skill: prd"
            assert repl.handle_input("/tasks") == "Unknown skill: task_breakdown"

    def test_no_agent(self):
        repl = CompanionREPL()
        repl.agent = None
        with patch(
            "video_processor.agent.skills.base.get_skill",
            return_value=MagicMock(),
        ):
            out = repl.handle_input("/run whatever")
        assert "Agent not initialised" in out

    def test_cannot_execute(self):
        repl = CompanionREPL()
        repl.agent = MagicMock()
        skill = MagicMock()
        skill.can_execute.return_value = False
        with patch(
            "video_processor.agent.skills.base.get_skill",
            return_value=skill,
        ):
            out = repl.handle_input("/run roadmap")
        assert "cannot execute" in out

    def test_success_returns_artifact(self):
        repl = CompanionREPL()
        repl.agent = MagicMock()
        skill = MagicMock()
        skill.can_execute.return_value = True
        skill.execute.return_value = Artifact(
            name="Roadmap",
            content="# Roadmap\n- item one",
            artifact_type="roadmap",
        )
        with patch(
            "video_processor.agent.skills.base.get_skill",
            return_value=skill,
        ):
            out = repl.handle_input("/run roadmap")
        assert "Roadmap" in out
        assert "roadmap" in out
        assert "# Roadmap" in out
        skill.execute.assert_called_once_with(repl.agent.context)

    def test_execution_error(self):
        repl = CompanionREPL()
        repl.agent = MagicMock()
        skill = MagicMock()
        skill.can_execute.return_value = True
        skill.execute.side_effect = RuntimeError("boom")
        with patch(
            "video_processor.agent.skills.base.get_skill",
            return_value=skill,
        ):
            out = repl.handle_input("/run roadmap")
        assert "Skill execution failed: boom" in out


# -----------------------------------------------------------------------
# /auth (real auth stack; only env + token dir controlled)
# -----------------------------------------------------------------------


class TestAuthCommand:
    def test_empty_lists_services(self):
        out = CompanionREPL().handle_input("/auth")
        assert "Usage: /auth SERVICE" in out
        assert "zoom" in out
        assert "notion" in out

    def test_unknown_service(self):
        out = CompanionREPL().handle_input("/auth notreal")
        assert "Unknown service: notreal" in out

    def test_success_via_api_key(self, tmp_path, monkeypatch):
        monkeypatch.setattr("video_processor.auth.TOKEN_DIR", tmp_path)
        with patch.dict(os.environ, {"NOTION_API_KEY": "secret-notion"}, clear=True):
            out = CompanionREPL().handle_input("/auth notion")
        assert out == "Notion authenticated (api_key)"

    def test_failure_when_no_credentials(self, tmp_path, monkeypatch):
        monkeypatch.setattr("video_processor.auth.TOKEN_DIR", tmp_path)
        with patch.dict(os.environ, {}, clear=True):
            out = CompanionREPL().handle_input("/auth zoom")
        assert "Zoom auth failed" in out


# -----------------------------------------------------------------------
# provider / model switching (ProviderManager mocked)
# -----------------------------------------------------------------------


class TestProviderModelSwitch:
    def test_provider_switch_success(self):
        with patch("video_processor.providers.manager.ProviderManager"):
            repl = CompanionREPL()
            out = repl.handle_input("/provider openai")
        assert out == "Switched to provider: openai"
        assert repl._provider_name == "openai"
        assert repl._chat_model is None
        assert repl.provider_manager is not None

    def test_provider_switch_failure(self):
        with patch(
            "video_processor.providers.manager.ProviderManager",
            side_effect=RuntimeError("no key"),
        ):
            out = CompanionREPL().handle_input("/provider bogus")
        assert out == "Failed to initialise provider: bogus"

    def test_model_switch_success(self):
        with patch("video_processor.providers.manager.ProviderManager"):
            repl = CompanionREPL()
            out = repl.handle_input("/model gpt-4o")
        assert out == "Switched to model: gpt-4o"
        assert repl._chat_model == "gpt-4o"

    def test_model_switch_failure(self):
        with patch(
            "video_processor.providers.manager.ProviderManager",
            side_effect=RuntimeError("no key"),
        ):
            out = CompanionREPL().handle_input("/model bogus-model")
        assert out == "Failed to initialise with model: bogus-model"

    def test_provider_list_marks_active(self):
        repl = CompanionREPL()
        repl.provider_manager = MagicMock()
        repl.provider_manager.provider = "anthropic"
        out = repl.handle_input("/provider")
        assert "(active)" in out
        assert "Current: anthropic" in out


# -----------------------------------------------------------------------
# chat with an initialised agent (LLM mocked)
# -----------------------------------------------------------------------


class TestChatWithAgent:
    def test_chat_success(self):
        repl = CompanionREPL()
        repl.provider_manager = MagicMock()
        repl.agent = MagicMock()
        repl.agent.chat.return_value = "The answer is 42."
        out = repl.handle_input("what is the answer?")
        assert out == "The answer is 42."
        repl.agent.chat.assert_called_once_with("what is the answer?")

    def test_chat_error(self):
        repl = CompanionREPL()
        repl.provider_manager = MagicMock()
        repl.agent = MagicMock()
        repl.agent.chat.side_effect = RuntimeError("kaboom")
        out = repl.handle_input("hi")
        assert "Chat error: kaboom" in out


# -----------------------------------------------------------------------
# provider/agent init edge cases + misc dispatch
# -----------------------------------------------------------------------


class TestInitAndDispatch:
    def test_init_provider_auto_maps_to_none(self):
        with patch("video_processor.providers.manager.ProviderManager") as mock_pm:
            repl = CompanionREPL()  # provider defaults to "auto"
            repl._init_provider()
        assert repl.provider_manager is mock_pm.return_value
        assert mock_pm.call_args.kwargs["provider"] is None

    def test_init_provider_failure(self):
        with patch(
            "video_processor.providers.manager.ProviderManager",
            side_effect=RuntimeError("nope"),
        ):
            repl = CompanionREPL(provider="openai")
            repl._init_provider()
        assert repl.provider_manager is None

    def test_init_agent_failure(self):
        with patch(
            "video_processor.agent.agent_loop.PlanningAgent",
            side_effect=RuntimeError("nope"),
        ):
            repl = CompanionREPL()
            repl._init_agent()
        assert repl.agent is None

    def test_empty_line_returns_empty(self):
        repl = CompanionREPL()
        assert repl.handle_input("") == ""
        assert repl.handle_input("   ") == ""

    def test_skills_none_registered(self):
        with patch(
            "video_processor.agent.skills.base.list_skills",
            return_value=[],
        ):
            out = CompanionREPL().handle_input("/skills")
        assert out == "No skills registered."


# -----------------------------------------------------------------------
# readline setup / history (readline is a boundary; home redirected to tmp)
# -----------------------------------------------------------------------


class TestReadline:
    def test_setup_readline_missing_module(self):
        repl = CompanionREPL()
        with patch.dict(sys.modules, {"readline": None}):
            repl._setup_readline()  # import readline -> ImportError -> early return
        assert not hasattr(repl, "_history_path")

    def test_completer_matches_commands(self, tmp_path, monkeypatch):
        import readline

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        previous = readline.get_completer()
        try:
            repl = CompanionREPL()
            repl._setup_readline()
            completer = readline.get_completer()
            assert completer("/he", 0) == "/help"
            assert completer("he", 0) == "help"  # leading slash stripped
            assert completer("/zzz", 0) is None
        finally:
            readline.set_completer(previous)

    def test_setup_readline_gnu_binding(self, tmp_path, monkeypatch):
        import readline

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        # Force the non-libedit (GNU readline) branch.
        monkeypatch.setattr(readline, "__doc__", "GNU readline library")
        with patch("readline.parse_and_bind") as mock_bind:
            CompanionREPL()._setup_readline()
        mock_bind.assert_any_call("tab: complete")

    def test_setup_readline_reads_existing_history(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        (tmp_path / ".planopticon_history").write_text("some old command\n")
        repl = CompanionREPL()
        repl._setup_readline()
        assert repl._history_path == tmp_path / ".planopticon_history"

    def test_setup_readline_history_read_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        (tmp_path / ".planopticon_history").write_text("cmd\n")
        with patch("readline.read_history_file", side_effect=OSError("boom")):
            CompanionREPL()._setup_readline()  # must not raise

    def test_save_history_writes_file(self, tmp_path):
        repl = CompanionREPL()
        repl._history_path = tmp_path / ".hist"
        repl._save_history()
        assert (tmp_path / ".hist").exists()

    def test_save_history_swallows_error(self, tmp_path):
        repl = CompanionREPL()
        repl._history_path = tmp_path / ".hist"
        with patch("readline.write_history_file", side_effect=OSError("boom")):
            repl._save_history()  # must not raise


# -----------------------------------------------------------------------
# run() main loop
# -----------------------------------------------------------------------


class TestRunLoop:
    def _isolate(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

    def test_run_immediate_eof(self, tmp_path, monkeypatch, capsys):
        self._isolate(monkeypatch, tmp_path)
        with (
            patch(
                "video_processor.integrators.graph_discovery.find_nearest_graph",
                return_value=None,
            ),
            patch("video_processor.providers.manager.ProviderManager", MagicMock()),
            patch("builtins.input", side_effect=EOFError),
        ):
            CompanionREPL().run()
        out = capsys.readouterr().out
        assert "PlanOpticon Companion" in out
        assert "Bye." in out

    def test_run_command_then_quit(self, tmp_path, monkeypatch, capsys):
        self._isolate(monkeypatch, tmp_path)
        with (
            patch(
                "video_processor.integrators.graph_discovery.find_nearest_graph",
                return_value=None,
            ),
            patch("video_processor.providers.manager.ProviderManager", MagicMock()),
            patch("builtins.input", side_effect=["/help", "/quit"]),
        ):
            CompanionREPL().run()
        out = capsys.readouterr().out
        assert "Available commands" in out
        assert "Bye." in out

    def test_run_keyboard_interrupt(self, tmp_path, monkeypatch, capsys):
        self._isolate(monkeypatch, tmp_path)
        with (
            patch(
                "video_processor.integrators.graph_discovery.find_nearest_graph",
                return_value=None,
            ),
            patch("video_processor.providers.manager.ProviderManager", MagicMock()),
            patch("builtins.input", side_effect=KeyboardInterrupt),
        ):
            CompanionREPL().run()
        assert "Bye." in capsys.readouterr().out
