"""Skill: Generate a product/project roadmap."""

from video_processor.agent.skills.base import (
    AgentContext,
    Artifact,
    Skill,
    register_skill,
)


class RoadmapSkill(Skill):
    name = "roadmap"
    description = "Generate a product/project roadmap"

    def execute(self, context: AgentContext, **kwargs) -> Artifact:
        stats = context.query_engine.stats()
        entities = context.query_engine.entities()
        relationships = context.query_engine.relationships()

        roadmap_types = {"milestone", "feature", "dependency"}
        relevant = [
            e for e in context.planning_entities if getattr(e, "type", "").lower() in roadmap_types
        ]

        parts = [
            "You are a product strategist. Using the following "
            "knowledge graph context, generate a product roadmap.",
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
            "## Milestones, Features & Dependencies",
        ]
        for e in relevant:
            parts.append(f"- [{getattr(e, 'type', 'unknown')}] {e}")

        if not relevant:
            parts.append(
                "(No pre-filtered entities; derive roadmap items from the full context above.)"
            )

        parts.append(
            "\nGenerate a markdown roadmap with:\n"
            "1. Vision & Strategy\n"
            "2. Phases (with timeline estimates)\n"
            "3. Key Dependencies\n"
            "4. A Mermaid Gantt chart summarizing the timeline\n\n"
            "Return ONLY the markdown."
        )

        prompt = "\n".join(parts)
        response = context.provider_manager.chat(messages=[{"role": "user", "content": prompt}])

        return Artifact(
            name="Roadmap",
            content=response,
            artifact_type="roadmap",
            format="markdown",
        )


register_skill(RoadmapSkill())
