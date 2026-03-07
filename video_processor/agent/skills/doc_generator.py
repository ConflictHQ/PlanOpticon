"""Skill: Generate technical documentation, ADRs, or meeting notes."""

from video_processor.agent.skills.base import (
    AgentContext,
    Artifact,
    Skill,
    register_skill,
)

_DOC_PROMPTS = {
    "technical_doc": (
        "Generate technical documentation with:\n"
        "1. Overview\n2. Architecture\n3. Components & Interfaces\n"
        "4. Data Flow\n5. Deployment & Configuration\n"
        "6. API Reference (if applicable)"
    ),
    "adr": (
        "Generate an Architecture Decision Record (ADR) with:\n"
        "1. Title\n2. Status (Proposed)\n3. Context\n"
        "4. Decision\n5. Consequences\n6. Alternatives Considered"
    ),
    "meeting_notes": (
        "Generate structured meeting notes with:\n"
        "1. Meeting Summary\n2. Key Discussion Points\n"
        "3. Decisions Made\n4. Action Items (with owners)\n"
        "5. Open Questions\n6. Next Steps"
    ),
}


class DocGeneratorSkill(Skill):
    name = "doc_generator"
    description = "Generate technical documentation, ADRs, or meeting notes"

    def execute(self, context: AgentContext, **kwargs) -> Artifact:
        doc_type = kwargs.get("doc_type", "technical_doc")
        stats = context.query_engine.stats()
        entities = context.query_engine.entities()
        relationships = context.query_engine.relationships()

        doc_instructions = _DOC_PROMPTS.get(doc_type, _DOC_PROMPTS["technical_doc"])
        doc_label = doc_type.replace("_", " ")

        parts = [
            f"You are a technical writer. Generate a {doc_label} "
            "from the following knowledge graph context.",
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
            "## Planning Entities",
        ]
        for e in context.planning_entities:
            parts.append(f"- {e}")

        parts.append(f"\n{doc_instructions}\n\nReturn ONLY the markdown.")

        prompt = "\n".join(parts)
        response = context.provider_manager.chat(messages=[{"role": "user", "content": prompt}])

        return Artifact(
            name=doc_label.title(),
            content=response,
            artifact_type="document",
            format="markdown",
            metadata={"doc_type": doc_type},
        )


register_skill(DocGeneratorSkill())
