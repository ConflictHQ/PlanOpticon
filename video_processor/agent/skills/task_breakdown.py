"""Skill: Break down goals into tasks with dependencies."""

from video_processor.agent.skills.base import (
    AgentContext,
    Artifact,
    Skill,
    register_skill,
)
from video_processor.utils.json_parsing import parse_json_from_response


class TaskBreakdownSkill(Skill):
    name = "task_breakdown"
    description = "Break down goals into tasks with dependencies"

    def execute(self, context: AgentContext, **kwargs) -> Artifact:
        stats = context.query_engine.stats()
        entities = context.query_engine.entities()
        relationships = context.query_engine.relationships()

        task_types = {"goal", "feature", "milestone"}
        relevant = [
            e for e in context.planning_entities if getattr(e, "type", "").lower() in task_types
        ]

        parts = [
            "You are a project manager. Using the following knowledge "
            "graph context, decompose goals and features into tasks.",
            "",
            "## Knowledge Graph Overview",
            stats.to_text(),
            "",
            "## Entities",
            entities.to_text(),
            "",
            "## Relationships",
            relationships.to_text(),
            "",
            "## Goals, Features & Milestones",
        ]
        for e in relevant:
            parts.append(f"- [{getattr(e, 'type', 'unknown')}] {e}")

        if not relevant:
            parts.append("(No pre-filtered entities; derive tasks from the full context above.)")

        parts.append(
            "\nReturn a JSON array of task objects with:\n"
            '- "id": string (e.g. "T1", "T2")\n'
            '- "title": string\n'
            '- "description": string\n'
            '- "depends_on": list of task id strings\n'
            '- "priority": "high" | "medium" | "low"\n'
            '- "estimate": string (e.g. "2d", "1w")\n'
            '- "assignee_role": string\n\n'
            "Return ONLY the JSON."
        )

        prompt = "\n".join(parts)
        response = context.provider_manager.chat(messages=[{"role": "user", "content": prompt}])
        parsed = parse_json_from_response(response)

        import json

        content = json.dumps(parsed, indent=2) if isinstance(parsed, list) else response

        return Artifact(
            name="Task Breakdown",
            content=content,
            artifact_type="task_list",
            format="json",
            metadata={"tasks": parsed if isinstance(parsed, list) else []},
        )


register_skill(TaskBreakdownSkill())
