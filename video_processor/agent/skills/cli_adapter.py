"""Skill: Push artifacts to external tools via their CLIs."""

import json
import shutil
import subprocess
from typing import List

from video_processor.agent.skills.base import AgentContext, Artifact, Skill, register_skill


def _format_github(artifact: Artifact) -> List[str]:
    """Convert artifact to gh CLI commands."""
    items = json.loads(artifact.content) if artifact.format == "json" else []
    cmds = []
    for item in items:
        cmd = f"gh issue create --title {json.dumps(item.get('title', ''))}"
        if item.get("body"):
            cmd += f" --body {json.dumps(item['body'])}"
        for label in item.get("labels", []):
            cmd += f" --label {json.dumps(label)}"
        cmds.append(cmd)
    return cmds


def _format_jira(artifact: Artifact) -> List[str]:
    """Convert artifact to jira-cli commands."""
    items = json.loads(artifact.content) if artifact.format == "json" else []
    return [
        f"jira issue create --summary {json.dumps(item.get('title', ''))}"
        f" --description {json.dumps(item.get('body', item.get('description', '')))}"
        for item in items
    ]


def _format_linear(artifact: Artifact) -> List[str]:
    """Convert artifact to linear CLI commands."""
    items = json.loads(artifact.content) if artifact.format == "json" else []
    return [
        f"linear issue create --title {json.dumps(item.get('title', ''))}"
        f" --description {json.dumps(item.get('body', item.get('description', '')))}"
        for item in items
    ]


_adapters = {"github": _format_github, "jira": _format_jira, "linear": _format_linear}


def run_commands(commands: List[str], dry_run: bool = True) -> List[dict]:
    """Execute CLI commands. In dry_run mode, just return what would run."""
    results = []
    for cmd in commands:
        if dry_run:
            results.append({"command": cmd, "status": "dry_run"})
        else:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            results.append(
                {
                    "command": cmd,
                    "returncode": proc.returncode,
                    "stdout": proc.stdout.strip(),
                    "stderr": proc.stderr.strip(),
                }
            )
    return results


class CLIAdapterSkill(Skill):
    name = "cli_adapter"
    description = "Push artifacts to external tools via their CLIs"

    def execute(self, context: AgentContext, **kwargs) -> Artifact:
        tool = kwargs.get("tool", "github")
        artifact = kwargs.get("artifact")
        if artifact is None and context.artifacts:
            artifact = context.artifacts[-1]
        if artifact is None:
            return Artifact(
                name="CLI Commands", content="[]", artifact_type="cli_commands", format="json"
            )

        formatter = _adapters.get(tool)
        if formatter is None:
            return Artifact(
                name="CLI Commands",
                content=json.dumps({"error": f"Unknown tool: {tool}"}),
                artifact_type="cli_commands",
                format="json",
            )

        cli_name = {"github": "gh", "jira": "jira", "linear": "linear"}[tool]
        available = shutil.which(cli_name) is not None
        commands = formatter(artifact)
        content = json.dumps({"tool": tool, "available": available, "commands": commands}, indent=2)
        return Artifact(
            name="CLI Commands", content=content, artifact_type="cli_commands", format="json"
        )


register_skill(CLIAdapterSkill())
