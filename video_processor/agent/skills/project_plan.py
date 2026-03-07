"""Skill: Generate a structured project plan from knowledge graph."""

from video_processor.agent.skills.base import (
    AgentContext,
    Artifact,
    Skill,
    register_skill,
)


def _group_entities_by_type(entities):
    """Group planning entities by their type."""
    grouped = {}
    for e in entities:
        etype = getattr(e, "type", "unknown")
        grouped.setdefault(etype, []).append(e)
    return grouped


class ProjectPlanSkill(Skill):
    name = "project_plan"
    description = "Generate a structured project plan from knowledge graph"

    def execute(self, context: AgentContext, **kwargs) -> Artifact:
        stats = context.query_engine.stats()
        entities = context.query_engine.entities()
        relationships = context.query_engine.relationships()
        grouped = _group_entities_by_type(context.planning_entities)

        parts = [
            "You are a project planning expert. Using the following "
            "knowledge graph context, generate a comprehensive "
            "project plan in markdown.",
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
            "## Planning Entities (by type)",
        ]
        for etype, elist in grouped.items():
            parts.append(f"\n### {etype}")
            for e in elist:
                parts.append(f"- {e}")

        parts.append(
            "\nGenerate a markdown project plan with:\n"
            "1. Executive Summary\n"
            "2. Goals & Objectives\n"
            "3. Scope\n"
            "4. Phases & Milestones\n"
            "5. Resource Requirements\n"
            "6. Risks & Mitigations\n"
            "7. Success Criteria\n\n"
            "Return ONLY the markdown."
        )

        prompt = "\n".join(parts)
        response = context.provider_manager.chat(messages=[{"role": "user", "content": prompt}])

        return Artifact(
            name="Project Plan",
            content=response,
            artifact_type="project_plan",
            format="markdown",
        )


register_skill(ProjectPlanSkill())
