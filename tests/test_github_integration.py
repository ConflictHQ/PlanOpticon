"""Tests for the github_issues agent skill (task -> issue conversion, gh push)."""

import json
from unittest.mock import MagicMock, patch

from video_processor.agent.skills.base import AgentContext, Artifact
from video_processor.agent.skills.github_integration import (
    GitHubIssuesSkill,
    _task_to_issue,
    push_to_github,
)


class TestTaskToIssue:
    def test_full_task_with_deps_and_labels(self):
        task = {
            "title": "Build API",
            "description": "Implement the REST API",
            "priority": "high",
            "estimate": "3d",
            "dependencies": ["Design schema", 2],
            "labels": ["backend"],
        }
        issue = _task_to_issue(task)
        assert issue["title"] == "Build API"
        assert "## Description\nImplement the REST API" in issue["body"]
        assert "**Priority:** high" in issue["body"]
        assert "**Estimate:** 3d" in issue["body"]
        assert "**Dependencies:** Design schema, 2" in issue["body"]
        # priority is always the first label, custom labels appended
        assert issue["labels"] == ["high", "backend"]

    def test_minimal_task_uses_defaults(self):
        issue = _task_to_issue({})
        assert issue["title"] == "Untitled task"
        assert "**Priority:** medium" in issue["body"]
        assert "**Estimate:** unknown" in issue["body"]
        assert "Dependencies" not in issue["body"]  # no deps -> no line
        assert issue["labels"] == ["medium"]

    def test_description_falls_back_to_title(self):
        issue = _task_to_issue({"title": "Only a title"})
        assert "## Description\nOnly a title" in issue["body"]


class TestPushToGithub:
    def test_returns_none_when_gh_missing(self):
        with patch(
            "video_processor.agent.skills.github_integration.shutil.which", return_value=None
        ):
            assert push_to_github(json.dumps([{"title": "x", "body": "y"}]), "org/repo") is None

    def test_creates_issues_via_gh(self):
        issues = json.dumps([{"title": "Bug", "body": "broken", "labels": ["bug", "p1"]}])
        proc = MagicMock(returncode=0, stdout="https://github.com/org/repo/issues/1\n", stderr="")
        with patch(
            "video_processor.agent.skills.github_integration.shutil.which",
            return_value="/usr/bin/gh",
        ):
            with patch(
                "video_processor.agent.skills.github_integration.subprocess.run",
                return_value=proc,
            ) as mock_run:
                results = push_to_github(issues, "org/repo")

        assert results[0]["returncode"] == 0
        assert results[0]["stdout"] == "https://github.com/org/repo/issues/1"
        cmd = mock_run.call_args.args[0]
        assert cmd[:5] == ["gh", "issue", "create", "--repo", "org/repo"]
        assert "--title" in cmd and "Bug" in cmd
        # both labels forwarded
        assert cmd.count("--label") == 2


class TestGitHubIssuesSkill:
    def test_execute_from_task_list_artifact(self):
        ctx = AgentContext()
        tasks = [
            {"title": "T1", "priority": "high"},
            {"title": "T2", "priority": "low", "dependencies": ["T1"]},
        ]
        ctx.artifacts = [
            Artifact(
                name="Tasks",
                content=json.dumps(tasks),
                artifact_type="task_list",
                format="json",
            )
        ]
        result = GitHubIssuesSkill().execute(ctx)
        assert result.artifact_type == "issues"
        issues = json.loads(result.content)
        assert [i["title"] for i in issues] == ["T1", "T2"]
        assert issues[0]["labels"] == ["high"]

    def test_execute_falls_back_to_planning_entities(self):
        ctx = AgentContext()
        ctx.artifacts = []
        ctx.planning_entities = ["Ship MVP", "Write docs"]
        result = GitHubIssuesSkill().execute(ctx)
        issues = json.loads(result.content)
        assert {i["title"] for i in issues} == {"Ship MVP", "Write docs"}
        # inline-generated tasks default to medium priority
        assert all(i["labels"] == ["medium"] for i in issues)
