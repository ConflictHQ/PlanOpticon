"""Tests for CLI query and kg commands, list-models, clear-cache, and auth.

These exercise real command paths against real on-disk graph fixtures
(SQLiteStore / JSON) built the same way the app builds them. Only the LLM
provider, model discovery, network auth, and cache boundaries are mocked.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from video_processor.cli.commands import _parse_filter_args, _print_result, cli
from video_processor.integrators.graph_query import QueryResult
from video_processor.integrators.graph_store import InMemoryStore, SQLiteStore
from video_processor.integrators.knowledge_graph import KnowledgeGraph
from video_processor.providers.base import ModelInfo


def _populate(store):
    store.merge_entity("Alice", "person", ["A software engineer"])
    store.merge_entity("Bob", "person", ["A product manager"])
    store.merge_entity("Python", "technology", ["A programming language"])
    store.merge_entity("Django", "technology", ["A web framework"])
    store.add_occurrence("Alice", "transcript_0", timestamp=1.0, text="Alice uses Python")
    store.add_relationship("Alice", "Python", "uses", content_source="transcript_0", timestamp=1.0)
    store.add_relationship("Alice", "Bob", "works_with")
    store.add_relationship("Django", "Python", "built_on")


def _build_db(path: Path) -> Path:
    store = SQLiteStore(path)
    _populate(store)
    store.close()
    return path


def _build_json(path: Path) -> Path:
    store = InMemoryStore()
    _populate(store)
    KnowledgeGraph(store=store).save(path)
    return path


class TestQueryCommand:
    def test_no_graph_found_errors(self):
        runner = CliRunner()
        with patch(
            "video_processor.integrators.graph_discovery.find_nearest_graph",
            return_value=None,
        ):
            result = runner.invoke(cli, ["query", "--mode", "direct"])
        assert result.exit_code == 1
        assert "No knowledge graph found" in result.output

    def test_db_path_missing_errors(self):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["query", "--db-path", "/nope/missing.db", "--mode", "direct", "stats"]
        )
        assert result.exit_code == 1
        assert "file not found" in result.output

    def test_stats_default_question_auto_mode(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        runner = CliRunner()
        # No question -> defaults to "stats"; default (auto) mode builds a provider
        # manager but never invokes it for the direct "stats" command.
        result = runner.invoke(cli, ["query", "--db-path", str(db)])
        assert result.exit_code == 0
        assert "entity_count" in result.output
        assert "relationship_count" in result.output

    def test_entities_filtered_by_type(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["query", "--db-path", str(db), "--mode", "direct", "entities --type technology"],
        )
        assert result.exit_code == 0
        assert "Python" in result.output
        assert "Django" in result.output
        assert "Alice" not in result.output

    def test_entities_filtered_by_name(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        runner = CliRunner()
        result = runner.invoke(
            cli, ["query", "--db-path", str(db), "--mode", "direct", "entities --name Alice"]
        )
        assert result.exit_code == 0
        assert "Alice" in result.output

    def test_neighbors(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        runner = CliRunner()
        result = runner.invoke(
            cli, ["query", "--db-path", str(db), "--mode", "direct", "neighbors Alice"]
        )
        assert result.exit_code == 0
        assert "Python" in result.output

    def test_relationships_by_source(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["query", "--db-path", str(db), "--mode", "direct", "relationships --source Alice"],
        )
        assert result.exit_code == 0
        assert "uses" in result.output or "works_with" in result.output

    def test_sources_and_provenance(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        runner = CliRunner()
        r1 = runner.invoke(cli, ["query", "--db-path", str(db), "--mode", "direct", "sources"])
        r2 = runner.invoke(
            cli, ["query", "--db-path", str(db), "--mode", "direct", "provenance Alice"]
        )
        assert r1.exit_code == 0
        assert r2.exit_code == 0

    def test_path_and_clusters(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        runner = CliRunner()
        r1 = runner.invoke(
            cli, ["query", "--db-path", str(db), "--mode", "direct", "path Alice Python"]
        )
        r2 = runner.invoke(cli, ["query", "--db-path", str(db), "--mode", "direct", "clusters"])
        assert r1.exit_code == 0
        assert r2.exit_code == 0

    def test_format_json(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        runner = CliRunner()
        result = runner.invoke(
            cli, ["query", "--db-path", str(db), "--mode", "direct", "--format", "json", "stats"]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["query_type"]

    def test_format_mermaid(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "query",
                "--db-path",
                str(db),
                "--mode",
                "direct",
                "--format",
                "mermaid",
                "neighbors Alice",
            ],
        )
        assert result.exit_code == 0
        assert "graph LR" in result.output

    def test_query_from_json_graph(self, tmp_path):
        graph = _build_json(tmp_path / "kg.json")
        runner = CliRunner()
        result = runner.invoke(cli, ["query", "--db-path", str(graph), "--mode", "direct", "stats"])
        assert result.exit_code == 0
        assert "entity_count" in result.output

    def test_direct_mode_nl_falls_back_to_entity_search(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        runner = CliRunner()
        # A non-command question in direct mode searches entities by name.
        result = runner.invoke(cli, ["query", "--db-path", str(db), "--mode", "direct", "Alice"])
        assert result.exit_code == 0
        assert "Alice" in result.output

    def test_interactive_repl(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["query", "--db-path", str(db), "--mode", "direct", "-I"],
            input="stats\nquit\n",
        )
        assert result.exit_code == 0
        assert "REPL" in result.output
        assert "entity_count" in result.output
        assert "Bye" in result.output


class TestQueryHelpers:
    def test_parse_filter_args_key_values(self):
        assert _parse_filter_args(["--type", "technology", "--limit", "10"]) == {
            "type": "technology",
            "limit": "10",
        }

    def test_parse_filter_args_bare_name(self):
        assert _parse_filter_args(["Alice"]) == {"name": "Alice"}

    def test_parse_filter_args_mixed(self):
        assert _parse_filter_args(["Alice", "--type", "person"]) == {
            "name": "Alice",
            "type": "person",
        }

    def test_parse_filter_args_dangling_flag_treated_as_name(self):
        # A trailing "--flag" with no following value falls through to the name branch.
        assert _parse_filter_args(["--type"]) == {"name": "--type"}

    def test_print_result_json(self, capsys):
        _print_result(QueryResult(data={"a": 1}, query_type="filter"), "json")
        assert json.loads(capsys.readouterr().out)["query_type"] == "filter"

    def test_print_result_mermaid(self, capsys):
        data = [{"name": "A", "type": "person"}, {"name": "B", "type": "person"}]
        _print_result(QueryResult(data=data, query_type="filter"), "mermaid")
        assert "graph LR" in capsys.readouterr().out

    def test_print_result_text(self, capsys):
        _print_result(QueryResult(data={"entity_count": 4}, query_type="filter"), "text")
        assert "entity_count: 4" in capsys.readouterr().out


class TestKgConvert:
    def test_db_to_json(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        dest = tmp_path / "out.json"
        runner = CliRunner()
        result = runner.invoke(cli, ["kg", "convert", str(db), str(dest)])
        assert result.exit_code == 0
        assert "Converted" in result.output
        assert dest.exists()
        data = json.loads(dest.read_text())
        assert any(n.get("name") == "Python" for n in data.get("nodes", []))

    def test_json_to_db(self, tmp_path):
        graph = _build_json(tmp_path / "kg.json")
        dest = tmp_path / "out.db"
        runner = CliRunner()
        result = runner.invoke(cli, ["kg", "convert", str(graph), str(dest)])
        assert result.exit_code == 0
        assert dest.exists()
        # Confirm the round-tripped db is readable and populated.
        store = SQLiteStore(dest)
        assert store.get_entity_count() == 4
        store.close()

    def test_same_format_errors(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        runner = CliRunner()
        result = runner.invoke(cli, ["kg", "convert", str(db), str(tmp_path / "other.db")])
        assert result.exit_code == 1
        assert "same format" in result.output

    def test_unsupported_source_format_errors(self, tmp_path):
        bad = tmp_path / "graph.txt"
        bad.write_text("not a graph")
        runner = CliRunner()
        result = runner.invoke(cli, ["kg", "convert", str(bad), str(tmp_path / "out.json")])
        assert result.exit_code == 1
        assert "Unsupported source format" in result.output


class TestKgSync:
    def test_db_to_json(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        out = tmp_path / "kg.json"
        runner = CliRunner()
        result = runner.invoke(cli, ["kg", "sync", str(db), str(out), "--direction", "db-to-json"])
        assert result.exit_code == 0
        assert "Synced" in result.output
        assert out.exists()

    def test_json_to_db(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        graph = _build_json(tmp_path / "src.json")
        runner = CliRunner()
        result = runner.invoke(
            cli, ["kg", "sync", str(db), str(graph), "--direction", "json-to-db"]
        )
        assert result.exit_code == 0
        assert "Synced" in result.output

    def test_auto_direction_defaults_json_path(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        runner = CliRunner()
        # No json arg + auto: json sibling doesn't exist yet -> db-to-json.
        result = runner.invoke(cli, ["kg", "sync", str(db)])
        assert result.exit_code == 0
        assert (tmp_path / "kg.json").exists()


class TestKgInspect:
    def test_inspect_db(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        runner = CliRunner()
        result = runner.invoke(cli, ["kg", "inspect", str(db)])
        assert result.exit_code == 0
        assert "Entities:" in result.output
        assert "Relationships:" in result.output
        assert "Entity types:" in result.output


class TestKgClassify:
    def test_classify_heuristic_text(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        runner = CliRunner()
        # provider=none skips the LLM entirely (heuristic-only classification).
        result = runner.invoke(cli, ["kg", "classify", str(db), "--provider", "none"])
        assert result.exit_code == 0

    def test_classify_heuristic_json(self, tmp_path):
        db = _build_db(tmp_path / "kg.db")
        runner = CliRunner()
        result = runner.invoke(
            cli, ["kg", "classify", str(db), "--provider", "none", "--format", "json"]
        )
        assert result.exit_code == 0
        assert isinstance(json.loads(result.output), list)


class TestKgFromExchange:
    def test_from_exchange_imports_db(self, tmp_path):
        from video_processor.exchange import PlanOpticonExchange, ProjectMeta
        from video_processor.models import Entity, Relationship

        ex = PlanOpticonExchange(
            project=ProjectMeta(name="Demo"),
            entities=[
                Entity(name="Python", type="technology", descriptions=["A language"]),
                Entity(name="Alice", type="person", descriptions=["Engineer"]),
            ],
            relationships=[Relationship(source="Alice", target="Python", type="uses")],
        )
        ex_path = tmp_path / "exchange.json"
        ex.to_file(ex_path)

        out_db = tmp_path / "imported.db"
        runner = CliRunner()
        result = runner.invoke(cli, ["kg", "from-exchange", str(ex_path), "-o", str(out_db)])
        assert result.exit_code == 0
        assert "Imported exchange" in result.output
        assert out_db.exists()
        store = SQLiteStore(out_db)
        assert store.get_entity_count() == 2
        store.close()


class TestListModels:
    def test_no_models_discovered(self):
        runner = CliRunner()
        with patch(
            "video_processor.providers.discovery.discover_available_models", return_value=[]
        ):
            result = runner.invoke(cli, ["list-models"])
        assert result.exit_code == 0
        assert "No models discovered" in result.output

    def test_lists_models_grouped_by_provider(self):
        models = [
            ModelInfo(id="gpt-4o", provider="openai", capabilities=["chat", "vision"]),
            ModelInfo(id="claude-haiku", provider="anthropic", capabilities=["chat"]),
        ]
        runner = CliRunner()
        with patch(
            "video_processor.providers.discovery.discover_available_models", return_value=models
        ):
            result = runner.invoke(cli, ["list-models"])
        assert result.exit_code == 0
        assert "OPENAI" in result.output
        assert "ANTHROPIC" in result.output
        assert "gpt-4o" in result.output
        assert "Total: 2 models across 2 providers" in result.output


class TestClearCache:
    def test_no_cache_dir_errors(self):
        runner = CliRunner()
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(cli, ["clear-cache"])
        assert result.exit_code == 1

    def test_nonexistent_cache_dir_returns(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["clear-cache", "--cache-dir", str(tmp_path / "nope")])
        assert result.exit_code == 0

    def test_empty_cache_dir_no_namespaces(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        runner = CliRunner()
        result = runner.invoke(cli, ["clear-cache", "--cache-dir", str(cache_dir)])
        assert result.exit_code == 0

    def test_clears_all_entries(self, tmp_path):
        from video_processor.utils.api_cache import ApiCache

        cache_dir = tmp_path / "cache"
        cache = ApiCache(cache_dir, "openai")
        cache.set("prompt-1", {"response": "hi"})
        entry = cache.get_cache_path("prompt-1")
        assert entry.exists()

        runner = CliRunner()
        result = runner.invoke(cli, ["clear-cache", "--cache-dir", str(cache_dir), "--all"])
        assert result.exit_code == 0
        assert not entry.exists()


class TestAuthCommand:
    def test_unknown_service_manager_none(self):
        runner = CliRunner()
        with patch("video_processor.auth.get_auth_manager", return_value=None):
            result = runner.invoke(cli, ["auth", "google"])
        assert result.exit_code == 1
        assert "Unknown service" in result.output

    def test_logout_clears_token(self):
        manager = MagicMock()
        runner = CliRunner()
        with patch("video_processor.auth.get_auth_manager", return_value=manager):
            result = runner.invoke(cli, ["auth", "github", "--logout"])
        assert result.exit_code == 0
        manager.clear_token.assert_called_once()
        assert "Cleared saved github token" in result.output

    def test_authenticate_success(self):
        manager = MagicMock()
        manager.authenticate.return_value = MagicMock(success=True, method="oauth")
        runner = CliRunner()
        with patch("video_processor.auth.get_auth_manager", return_value=manager):
            result = runner.invoke(cli, ["auth", "zoom"])
        assert result.exit_code == 0
        assert "Zoom authentication successful (oauth)" in result.output

    def test_authenticate_failure(self):
        manager = MagicMock()
        manager.authenticate.return_value = MagicMock(success=False, error="bad creds")
        runner = CliRunner()
        with patch("video_processor.auth.get_auth_manager", return_value=manager):
            result = runner.invoke(cli, ["auth", "notion"])
        assert result.exit_code == 1
        assert "authentication failed: bad creds" in result.output
