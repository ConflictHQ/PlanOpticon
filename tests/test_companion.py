"""Tests for the CompanionREPL (without launching the loop)."""

from unittest.mock import patch

from video_processor.cli.companion import CompanionREPL


class TestImport:
    def test_import(self):
        from video_processor.cli import companion  # noqa: F401

        assert hasattr(companion, "CompanionREPL")


class TestConstructor:
    def test_defaults(self):
        repl = CompanionREPL()
        assert repl.kg is None
        assert repl.query_engine is None
        assert repl.agent is None
        assert repl.provider_manager is None

    def test_explicit_args(self):
        repl = CompanionREPL(
            kb_paths=["/tmp/fake.db"],
            provider="openai",
            chat_model="gpt-4",
        )
        assert repl._kb_paths == ["/tmp/fake.db"]
        assert repl._provider_name == "openai"
        assert repl._chat_model == "gpt-4"


class TestAutoDiscovery:
    @patch(
        "video_processor.integrators.graph_discovery.find_nearest_graph",
        return_value=None,
    )
    def test_no_graph_found(self, mock_find):
        repl = CompanionREPL()
        repl._discover()
        assert repl.query_engine is None
        assert repl.kg is None
        mock_find.assert_called_once()


class TestHandleHelp:
    def test_handle_help(self):
        repl = CompanionREPL()
        output = repl.handle_input("/help")
        assert "Available commands" in output
        assert "/status" in output
        assert "/skills" in output
        assert "/entities" in output
        assert "/quit" in output


class TestHandleStatus:
    def test_handle_status_no_kg(self):
        repl = CompanionREPL()
        output = repl.handle_input("/status")
        assert "Workspace status" in output
        assert "not loaded" in output


class TestHandleSkills:
    def test_handle_skills(self):
        repl = CompanionREPL()
        output = repl.handle_input("/skills")
        # Either lists skills or says none registered
        assert "skills" in output.lower() or "No skills" in output


class TestHandleQuit:
    def test_quit(self):
        repl = CompanionREPL()
        assert repl.handle_input("/quit") == "__QUIT__"

    def test_exit(self):
        repl = CompanionREPL()
        assert repl.handle_input("/exit") == "__QUIT__"

    def test_bare_quit(self):
        repl = CompanionREPL()
        assert repl.handle_input("quit") == "__QUIT__"

    def test_bare_exit(self):
        repl = CompanionREPL()
        assert repl.handle_input("exit") == "__QUIT__"

    def test_bare_bye(self):
        repl = CompanionREPL()
        assert repl.handle_input("bye") == "__QUIT__"

    def test_bare_q(self):
        repl = CompanionREPL()
        assert repl.handle_input("q") == "__QUIT__"


class TestHandleUnknownSlash:
    def test_unknown_command(self):
        repl = CompanionREPL()
        output = repl.handle_input("/foobar")
        assert "Unknown command" in output
        assert "/help" in output


class TestHandleChatNoProvider:
    def test_chat_no_provider(self):
        repl = CompanionREPL()
        output = repl.handle_input("What is this project about?")
        assert "LLM provider" in output or "API" in output
        # Should not crash


class TestHandleEntitiesNoKG:
    def test_entities_no_kg(self):
        repl = CompanionREPL()
        output = repl.handle_input("/entities")
        assert "No knowledge graph loaded" in output

    def test_search_no_kg(self):
        repl = CompanionREPL()
        output = repl.handle_input("/search python")
        assert "No knowledge graph loaded" in output

    def test_neighbors_no_kg(self):
        repl = CompanionREPL()
        output = repl.handle_input("/neighbors Alice")
        assert "No knowledge graph loaded" in output


class TestProviderCommand:
    def test_provider_list(self):
        repl = CompanionREPL()
        output = repl.handle_input("/provider")
        assert "Available providers" in output
        assert "openai" in output
        assert "anthropic" in output

    def test_provider_switch(self):
        repl = CompanionREPL()
        output = repl.handle_input("/provider openai")
        # Will fail to init without key, but shouldn't crash
        assert "openai" in output.lower()

    def test_model_show(self):
        repl = CompanionREPL()
        output = repl.handle_input("/model")
        assert "Current model" in output

    def test_model_switch(self):
        repl = CompanionREPL()
        output = repl.handle_input("/model gpt-4o")
        # Will fail without provider, but shouldn't crash
        assert "gpt-4o" in output

    def test_help_includes_provider(self):
        repl = CompanionREPL()
        output = repl.handle_input("/help")
        assert "/provider" in output
        assert "/model" in output
