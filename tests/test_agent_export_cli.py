"""Tests for the artifact_export and cli_adapter agent skills.

Both are pure logic (no LLM). Only shutil.which / subprocess are mocked.
"""

import json
from unittest.mock import MagicMock, patch

from video_processor.agent.skills.artifact_export import (
    ArtifactExportSkill,
    _write_artifact,
    export_artifacts,
)
from video_processor.agent.skills.base import AgentContext, Artifact
from video_processor.agent.skills.cli_adapter import (
    CLIAdapterSkill,
    _format_github,
    _format_jira,
    _format_linear,
    run_commands,
)


def _artifact(name, content, artifact_type, fmt="markdown"):
    return Artifact(name=name, content=content, artifact_type=artifact_type, format=fmt)


class TestWriteArtifact:
    def test_known_type_maps_to_fixed_filename(self, tmp_path):
        art = _artifact("Plan", "# Plan\nbody", "project_plan")
        entry = _write_artifact(art, tmp_path)
        dest = tmp_path / "project_plan.md"
        assert dest.read_text() == "# Plan\nbody"
        assert entry["file"] == str(dest)
        assert entry["artifact_type"] == "project_plan"

    def test_document_type_goes_to_docs_subdir(self, tmp_path):
        art = _artifact("My Notes", "content", "document", fmt="markdown")
        entry = _write_artifact(art, tmp_path)
        dest = tmp_path / "docs" / "my_notes.md"
        assert dest.exists()
        assert entry["file"] == str(dest)

    def test_document_json_uses_json_extension(self, tmp_path):
        art = _artifact("Data Set", "{}", "document", fmt="json")
        _write_artifact(art, tmp_path)
        assert (tmp_path / "docs" / "data_set.json").exists()

    def test_unknown_type_falls_back_to_slugged_name(self, tmp_path):
        art = _artifact("Weird/Thing Here", "x", "mystery", fmt="markdown")
        entry = _write_artifact(art, tmp_path)
        dest = tmp_path / "weird_thing_here.md"
        assert dest.exists()
        assert entry["name"] == "Weird/Thing Here"


class TestExportArtifacts:
    def test_export_writes_files_and_manifest(self, tmp_path):
        artifacts = [
            _artifact("Plan", "# Plan", "project_plan"),
            _artifact("Tasks", "[]", "task_list", fmt="json"),
        ]
        manifest = export_artifacts(artifacts, tmp_path / "out")
        out = tmp_path / "out"
        assert manifest["artifact_count"] == 2
        assert (out / "project_plan.md").exists()
        assert (out / "tasks.json").exists()
        written = json.loads((out / "manifest.json").read_text())
        assert written["artifact_count"] == 2
        assert len(written["files"]) == 2


class TestArtifactExportSkill:
    def test_execute_returns_manifest_artifact(self, tmp_path):
        ctx = AgentContext()
        ctx.artifacts = [_artifact("Roadmap", "# Roadmap", "roadmap")]
        skill = ArtifactExportSkill()
        result = skill.execute(ctx, output_dir=str(tmp_path / "plan"))
        assert result.artifact_type == "export_manifest"
        assert result.format == "json"
        parsed = json.loads(result.content)
        assert parsed["artifact_count"] == 1
        assert (tmp_path / "plan" / "roadmap.md").exists()
        assert (tmp_path / "plan" / "manifest.json").exists()


class TestFormatters:
    def test_format_github_builds_gh_commands(self):
        art = _artifact(
            "Issues",
            json.dumps([{"title": "Bug A", "body": "broken", "labels": ["bug", "p1"]}]),
            "issues",
            fmt="json",
        )
        cmds = _format_github(art)
        assert len(cmds) == 1
        assert cmds[0].startswith("gh issue create --title ")
        assert '"Bug A"' in cmds[0]
        assert "--body" in cmds[0]
        assert cmds[0].count("--label") == 2

    def test_format_github_non_json_returns_empty(self):
        art = _artifact("Issues", "not json", "issues", fmt="markdown")
        assert _format_github(art) == []

    def test_format_jira_and_linear(self):
        content = json.dumps([{"title": "Task", "description": "do it"}])
        jira = _format_jira(_artifact("t", content, "issues", fmt="json"))
        linear = _format_linear(_artifact("t", content, "issues", fmt="json"))
        assert jira[0].startswith("jira issue create --summary ")
        assert '"do it"' in jira[0]
        assert linear[0].startswith("linear issue create --title ")
        assert '"do it"' in linear[0]


class TestRunCommands:
    def test_dry_run_reports_without_executing(self):
        results = run_commands(["gh issue create --title x"], dry_run=True)
        assert results == [{"command": "gh issue create --title x", "status": "dry_run"}]

    def test_real_run_captures_output(self):
        proc = MagicMock(returncode=0, stdout="created\n", stderr="")
        with patch(
            "video_processor.agent.skills.cli_adapter.subprocess.run", return_value=proc
        ) as mock_run:
            results = run_commands(["gh issue create --title x"], dry_run=False)
        mock_run.assert_called_once()
        assert results[0]["returncode"] == 0
        assert results[0]["stdout"] == "created"


class TestCLIAdapterSkill:
    def test_no_artifact_returns_empty(self):
        ctx = AgentContext()
        ctx.artifacts = []
        result = CLIAdapterSkill().execute(ctx)
        assert result.content == "[]"

    def test_unknown_tool_returns_error(self):
        ctx = AgentContext()
        art = _artifact("Issues", "[]", "issues", fmt="json")
        result = CLIAdapterSkill().execute(ctx, tool="bitbucket", artifact=art)
        assert json.loads(result.content)["error"] == "Unknown tool: bitbucket"

    def test_github_tool_reports_availability_and_commands(self):
        ctx = AgentContext()
        art = _artifact(
            "Issues",
            json.dumps([{"title": "A"}, {"title": "B"}]),
            "issues",
            fmt="json",
        )
        with patch(
            "video_processor.agent.skills.cli_adapter.shutil.which", return_value="/usr/bin/gh"
        ):
            result = CLIAdapterSkill().execute(ctx, tool="github", artifact=art)
        parsed = json.loads(result.content)
        assert parsed["tool"] == "github"
        assert parsed["available"] is True
        assert len(parsed["commands"]) == 2

    def test_falls_back_to_last_context_artifact_when_unavailable(self):
        ctx = AgentContext()
        ctx.artifacts = [_artifact("Issues", json.dumps([{"title": "A"}]), "issues", fmt="json")]
        with patch("video_processor.agent.skills.cli_adapter.shutil.which", return_value=None):
            result = CLIAdapterSkill().execute(ctx, tool="github")
        parsed = json.loads(result.content)
        assert parsed["available"] is False
        assert len(parsed["commands"]) == 1
