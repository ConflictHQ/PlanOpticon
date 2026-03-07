"""Tests for the CLI commands (help text, version, option presence)."""

from click.testing import CliRunner

from video_processor.cli.commands import cli


class TestCLIRoot:
    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "PlanOpticon" in result.output
        assert "0.4.0" in result.output  # matches @click.version_option

    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "PlanOpticon" in result.output
        assert "analyze" in result.output
        assert "query" in result.output
        assert "agent" in result.output
        assert "kg" in result.output
        assert "gws" in result.output
        assert "m365" in result.output
        assert "ingest" in result.output
        assert "batch" in result.output


class TestAnalyzeHelp:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "--input" in result.output or "-i" in result.output
        assert "--output" in result.output or "-o" in result.output
        assert "--depth" in result.output
        assert "--provider" in result.output
        assert "--output-format" in result.output
        assert "--templates-dir" in result.output
        assert "--speakers" in result.output
        assert "--vision-model" in result.output
        assert "--chat-model" in result.output
        assert "--sampling-rate" in result.output
        assert "--change-threshold" in result.output
        assert "--periodic-capture" in result.output


class TestQueryHelp:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["query", "--help"])
        assert result.exit_code == 0
        assert "--db-path" in result.output
        assert "--mode" in result.output
        assert "--format" in result.output
        assert "--interactive" in result.output or "-I" in result.output
        assert "--provider" in result.output
        assert "--chat-model" in result.output
        assert "QUESTION" in result.output


class TestAgentHelp:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["agent", "--help"])
        assert result.exit_code == 0
        assert "--kb" in result.output
        assert "--interactive" in result.output or "-I" in result.output
        assert "--export" in result.output
        assert "--provider" in result.output
        assert "--chat-model" in result.output
        assert "REQUEST" in result.output


class TestKGHelp:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["kg", "--help"])
        assert result.exit_code == 0
        assert "convert" in result.output
        assert "Knowledge graph" in result.output

    def test_convert_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["kg", "convert", "--help"])
        assert result.exit_code == 0
        assert "SOURCE_PATH" in result.output
        assert "DEST_PATH" in result.output


class TestIngestHelp:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "INPUT_PATH" in result.output
        assert "--output" in result.output or "-o" in result.output
        assert "--db-path" in result.output
        assert "--recursive" in result.output
        assert "--provider" in result.output
        assert "--chat-model" in result.output


class TestBatchHelp:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["batch", "--help"])
        assert result.exit_code == 0
        assert "--input-dir" in result.output or "-i" in result.output
        assert "--output" in result.output or "-o" in result.output
        assert "--depth" in result.output
        assert "--pattern" in result.output
        assert "--source" in result.output
        assert "--folder-id" in result.output


class TestAgentAnalyzeHelp:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["agent-analyze", "--help"])
        assert result.exit_code == 0
        assert "--input" in result.output or "-i" in result.output
        assert "--output" in result.output or "-o" in result.output
        assert "--depth" in result.output
        assert "--provider" in result.output


class TestListModelsHelp:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["list-models", "--help"])
        assert result.exit_code == 0
        assert "Discover" in result.output or "models" in result.output


class TestClearCacheHelp:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["clear-cache", "--help"])
        assert result.exit_code == 0
        assert "--cache-dir" in result.output
        assert "--older-than" in result.output
        assert "--all" in result.output


class TestGWSHelp:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["gws", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "fetch" in result.output
        assert "ingest" in result.output

    def test_list_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["gws", "list", "--help"])
        assert result.exit_code == 0
        assert "--folder-id" in result.output
        assert "--query" in result.output

    def test_ingest_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["gws", "ingest", "--help"])
        assert result.exit_code == 0
        assert "--folder-id" in result.output
        assert "--doc-id" in result.output
        assert "--db-path" in result.output


class TestM365Help:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["m365", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "fetch" in result.output
        assert "ingest" in result.output

    def test_list_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["m365", "list", "--help"])
        assert result.exit_code == 0
        assert "--web-url" in result.output
        assert "--folder-url" in result.output
        assert "--recursive" in result.output

    def test_ingest_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["m365", "ingest", "--help"])
        assert result.exit_code == 0
        assert "--web-url" in result.output
        assert "--file-id" in result.output
        assert "--db-path" in result.output


class TestAuthHelp:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["auth", "--help"])
        assert result.exit_code == 0
        assert "google" in result.output
        assert "dropbox" in result.output
