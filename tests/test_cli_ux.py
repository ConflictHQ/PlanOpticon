"""Tests for CLI UX improvements — doctor, init wizard, and tab completion."""

import os
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from video_processor.cli.commands import cli
from video_processor.cli.companion import CompanionREPL
from video_processor.cli.doctor import (
    check_api_keys,
    check_dotenv,
    check_ffmpeg,
    check_optional_deps,
    check_python_version,
    format_results,
    run_all_checks,
)


class TestDoctor:
    def test_check_python_version(self):
        name, status, detail = check_python_version()
        assert name == "Python"
        assert status == "ok"

    def test_check_ffmpeg_found(self):
        with patch("video_processor.cli.doctor.shutil") as mock_shutil:
            mock_shutil.which.return_value = "/usr/bin/ffmpeg"
            name, status, detail = check_ffmpeg()
            assert status == "ok"

    def test_check_ffmpeg_missing(self):
        with patch("video_processor.cli.doctor.shutil") as mock_shutil:
            mock_shutil.which.return_value = None
            name, status, detail = check_ffmpeg()
            assert status == "missing"

    def test_check_api_keys_with_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test1234567890"}):
            results = check_api_keys()
            openai = [r for r in results if r[0].strip() == "OpenAI"]
            assert len(openai) == 1
            assert openai[0][1] == "ok"
            assert "sk-t" in openai[0][2]

    def test_check_api_keys_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            results = check_api_keys()
            openai = [r for r in results if "OpenAI" in r[0]]
            assert openai[0][1] == "not set"

    def test_check_dotenv_exists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("KEY=val\n")
        name, status, detail = check_dotenv()
        assert status == "ok"

    def test_check_dotenv_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        name, status, detail = check_dotenv()
        assert status == "not found"

    def test_check_optional_deps(self):
        results = check_optional_deps()
        assert len(results) > 0
        # All results should have 3 elements
        for name, status, detail in results:
            assert status in ("ok", "not installed")

    def test_format_results(self):
        results = [
            ("Python", "ok", "3.12.0"),
            ("FFmpeg", "missing", "Install it"),
        ]
        output = format_results(results)
        assert "PlanOpticon Doctor" in output
        assert "[ok]" in output
        assert "[XX]" in output

    def test_run_all_checks(self):
        with patch(
            "video_processor.integrators.graph_discovery.find_nearest_graph",
            return_value=None,
        ):
            results = run_all_checks()
            assert len(results) > 5
            # Should have section headers
            sections = [r for r in results if r[1] == "section"]
            assert len(sections) >= 2

    def test_doctor_cli_command(self):
        runner = CliRunner()
        with patch(
            "video_processor.integrators.graph_discovery.find_nearest_graph",
            return_value=None,
        ):
            result = runner.invoke(cli, ["doctor"])
            assert result.exit_code == 0
            assert "PlanOpticon Doctor" in result.output


class TestInitWizard:
    def test_init_cli_command_exists(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["init", "--help"])
        assert result.exit_code == 0
        assert "setup wizard" in result.output.lower() or "wizard" in result.output.lower()

    def test_wizard_provider_selection(self):
        """Test the wizard runs with simulated input."""
        runner = CliRunner()
        # Select provider 1 (OpenAI), enter a key, decline additional providers
        result = runner.invoke(
            cli,
            ["init"],
            input="1\nsk-test-key-1234567890\nn\n",
        )
        assert result.exit_code == 0
        assert "Setup complete" in result.output

    def test_wizard_ollama_provider(self):
        """Test selecting Ollama (no API key needed)."""
        runner = CliRunner()
        with patch(
            "video_processor.cli.init_wizard.shutil.which",
            return_value="/usr/local/bin/ollama",
        ):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="NAME\nllama3\n")
                result = runner.invoke(
                    cli,
                    ["init"],
                    input="4\nn\n",
                )
                assert result.exit_code == 0
                assert "Setup complete" in result.output


class TestCompanionTabCompletion:
    def test_commands_list_exists(self):
        assert len(CompanionREPL.COMMANDS) > 10
        assert "/help" in CompanionREPL.COMMANDS
        assert "/quit" in CompanionREPL.COMMANDS

    def test_setup_readline_no_crash(self):
        """Readline setup should not crash even if readline is unavailable."""
        repl = CompanionREPL()
        # Just ensure it doesn't raise
        repl._setup_readline()

    def test_all_commands_in_dispatch(self):
        """Every command in COMMANDS should be handled by handle_input."""
        repl = CompanionREPL()
        for cmd in CompanionREPL.COMMANDS:
            if cmd in ("/quit", "/exit"):
                result = repl.handle_input(cmd)
                assert result == "__QUIT__"
            else:
                result = repl.handle_input(cmd)
                assert "Unknown command" not in result, f"{cmd} not handled"
