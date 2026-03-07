"""Skill: Export artifacts in agent-ready formats to a directory structure."""

import json
from pathlib import Path

from video_processor.agent.skills.base import AgentContext, Artifact, Skill, register_skill

# Maps artifact_type to output filename
_TYPE_TO_FILE = {
    "project_plan": "project_plan.md",
    "prd": "prd.md",
    "roadmap": "roadmap.md",
    "task_list": "tasks.json",
    "issues": "issues.json",
    "requirements": "requirements.json",
}


def _write_artifact(artifact: Artifact, output_dir: Path) -> dict:
    """Write a single artifact to the appropriate file. Returns manifest entry."""
    filename = _TYPE_TO_FILE.get(artifact.artifact_type)
    if filename:
        dest = output_dir / filename
    elif artifact.artifact_type == "document":
        docs_dir = output_dir / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        safe_name = artifact.name.replace(" ", "_").replace("/", "_").lower()
        ext = ".json" if artifact.format == "json" else ".md"
        dest = docs_dir / f"{safe_name}{ext}"
    else:
        safe_name = artifact.name.replace(" ", "_").replace("/", "_").lower()
        ext = ".json" if artifact.format == "json" else ".md"
        dest = output_dir / f"{safe_name}{ext}"

    dest.write_text(artifact.content, encoding="utf-8")
    return {
        "file": str(dest),
        "name": artifact.name,
        "artifact_type": artifact.artifact_type,
        "format": artifact.format,
    }


class ArtifactExportSkill(Skill):
    name = "artifact_export"
    description = "Export artifacts in agent-ready formats"

    def execute(self, context: AgentContext, **kwargs) -> Artifact:
        output_dir = Path(kwargs.get("output_dir", "plan"))
        output_dir.mkdir(parents=True, exist_ok=True)

        manifest_entries = []
        for artifact in context.artifacts:
            entry = _write_artifact(artifact, output_dir)
            manifest_entries.append(entry)

        manifest = {
            "artifact_count": len(manifest_entries),
            "output_dir": str(output_dir),
            "files": manifest_entries,
        }
        manifest_path = output_dir / "manifest.json"
        manifest_json = json.dumps(manifest, indent=2)
        manifest_path.write_text(manifest_json, encoding="utf-8")

        return Artifact(
            name="Export Manifest",
            content=manifest_json,
            artifact_type="export_manifest",
            format="json",
        )


register_skill(ArtifactExportSkill())


def export_artifacts(artifacts: list, output_dir: Path) -> dict:
    """Standalone helper: export a list of Artifact objects to a directory."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries = []
    for artifact in artifacts:
        entry = _write_artifact(artifact, output_dir)
        manifest_entries.append(entry)

    manifest = {
        "artifact_count": len(manifest_entries),
        "output_dir": str(output_dir),
        "files": manifest_entries,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
