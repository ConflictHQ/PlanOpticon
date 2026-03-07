"""Skill: Generate a product requirements document (PRD) / feature spec."""

from video_processor.agent.skills.base import (
    AgentContext,
    Artifact,
    Skill,
    register_skill,
)


class PRDSkill(Skill):
    name = "prd"
    description = "Generate a product requirements document (PRD) / feature spec"

    def execute(self, context: AgentContext, **kwargs) -> Artifact:
        stats = context.query_engine.stats()
        entities = context.query_engine.entities()
        relationships = context.query_engine.relationships()

        relevant_types = {"requirement", "feature", "constraint"}
        filtered = [
            e for e in context.planning_entities if getattr(e, "type", "").lower() in relevant_types
        ]

        parts = [
            "You are a product manager. Using the following knowledge "
            "graph context, generate a product requirements document.",
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
            "## Relevant Planning Entities",
        ]
        for e in filtered:
            parts.append(f"- [{getattr(e, 'type', 'unknown')}] {e}")

        if not filtered:
            parts.append(
                "(No pre-filtered entities; derive requirements from the full context above.)"
            )

        parts.append(
            "\nGenerate a PRD with:\n"
            "1. Problem Statement\n"
            "2. User Stories\n"
            "3. Functional Requirements\n"
            "4. Non-Functional Requirements\n"
            "5. Acceptance Criteria\n"
            "6. Out of Scope\n\n"
            "Return ONLY the markdown."
        )

        prompt = "\n".join(parts)
        response = context.provider_manager.chat(messages=[{"role": "user", "content": prompt}])

        return Artifact(
            name="Product Requirements Document",
            content=response,
            artifact_type="prd",
            format="markdown",
        )


register_skill(PRDSkill())
