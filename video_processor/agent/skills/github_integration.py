"""Skill: Generate GitHub issues from task breakdown artifacts."""

import json
import shutil
import subprocess
from typing import List, Optional

from video_processor.agent.skills.base import AgentContext, Artifact, Skill, register_skill


def _task_to_issue(task: dict) -> dict:
    """Convert a task dict to a GitHub issue object."""
    deps = task.get("dependencies", [])
    body_parts = [
        f"## Description\n{task.get('description', task.get('title', ''))}",
        f"**Priority:** {task.get('priority', 'medium')}",
        f"**Estimate:** {task.get('estimate', 'unknown')}",
    ]
    if deps:
        body_parts.append(f"**Dependencies:** {', '.join(str(d) for d in deps)}")
    labels = [task.get("priority", "medium")]
    if task.get("labels"):
        labels.extend(task["labels"])
    return {
        "title": task.get("title", "Untitled task"),
        "body": "\n\n".join(body_parts),
        "labels": labels,
    }


def push_to_github(issues_json: str, repo: str) -> Optional[List[dict]]:
    """Shell out to `gh issue create` for each issue. Returns None if gh unavailable."""
    if not shutil.which("gh"):
        return None
    issues = json.loads(issues_json)
    results = []
    for issue in issues:
        cmd = [
            "gh",
            "issue",
            "create",
            "--repo",
            repo,
            "--title",
            issue["title"],
            "--body",
            issue["body"],
        ]
        for label in issue.get("labels", []):
            cmd.extend(["--label", label])
        proc = subprocess.run(cmd, capture_output=True, text=True)
        results.append(
            {
                "title": issue["title"],
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
            }
        )
    return results


class GitHubIssuesSkill(Skill):
    name = "github_issues"
    description = "Generate GitHub issues from task breakdown"

    def execute(self, context: AgentContext, **kwargs) -> Artifact:
        task_artifact = next((a for a in context.artifacts if a.artifact_type == "task_list"), None)
        if task_artifact:
            tasks = json.loads(task_artifact.content)
        else:
            # Generate minimal task list inline from planning entities
            tasks = [
                {
                    "title": str(e),
                    "description": str(e),
                    "priority": "medium",
                    "estimate": "unknown",
                }
                for e in context.planning_entities
            ]

        issues = [_task_to_issue(t) for t in tasks]
        content = json.dumps(issues, indent=2)
        return Artifact(
            name="GitHub Issues",
            content=content,
            artifact_type="issues",
            format="json",
        )


register_skill(GitHubIssuesSkill())
