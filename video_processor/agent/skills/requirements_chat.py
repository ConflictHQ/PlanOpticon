"""Skill: Interactive requirements gathering via guided questions."""

import json

from video_processor.agent.skills.base import (
    AgentContext,
    Artifact,
    Skill,
    register_skill,
)
from video_processor.utils.json_parsing import parse_json_from_response


class RequirementsChatSkill(Skill):
    name = "requirements_chat"
    description = "Interactive requirements gathering via guided questions"

    def execute(self, context: AgentContext, **kwargs) -> Artifact:
        """Generate a structured requirements questionnaire."""
        stats = context.query_engine.stats()
        entities = context.query_engine.entities()

        parts = [
            "You are a requirements analyst. Based on the following "
            "knowledge graph context, generate a requirements "
            "gathering questionnaire.",
            "",
            "## Knowledge Graph Overview",
            stats.to_text(),
            "",
            "## Entities",
            entities.to_text(),
            "",
            "## Planning Entities",
        ]
        for e in context.planning_entities:
            parts.append(f"- {e}")

        parts.append(
            '\nGenerate a JSON object with a "questions" array. '
            "Each question should have:\n"
            '- "id": string (e.g. "Q1")\n'
            '- "category": "goals"|"constraints"|"priorities"|"scope"\n'
            '- "question": string\n'
            '- "context": string (why this matters)\n\n'
            "Include 8-12 targeted questions.\n\n"
            "Return ONLY the JSON."
        )

        prompt = "\n".join(parts)
        response = context.provider_manager.chat(messages=[{"role": "user", "content": prompt}])
        parsed = parse_json_from_response(response)
        content = json.dumps(parsed, indent=2) if not isinstance(parsed, str) else parsed

        return Artifact(
            name="Requirements Questionnaire",
            content=content,
            artifact_type="requirements",
            format="json",
            metadata={"stage": "questionnaire"},
        )

    def gather_requirements(self, context: AgentContext, answers: dict) -> dict:
        """Take Q&A pairs and synthesize structured requirements."""
        stats = context.query_engine.stats()

        qa_text = ""
        for qid, answer in answers.items():
            qa_text += f"- {qid}: {answer}\n"

        parts = [
            "You are a requirements analyst. Based on the knowledge "
            "graph context and the answered questions, synthesize "
            "structured requirements.",
            "",
            "## Knowledge Graph Overview",
            stats.to_text(),
            "",
            "## Answers",
            qa_text,
            "Return a JSON object with:\n"
            '- "goals": list of goal strings\n'
            '- "constraints": list of constraint strings\n'
            '- "priorities": list (ordered high to low)\n'
            '- "scope": {"in_scope": [...], "out_of_scope": [...]}\n\n'
            "Return ONLY the JSON.",
        ]

        prompt = "\n".join(parts)
        response = context.provider_manager.chat(messages=[{"role": "user", "content": prompt}])
        result = parse_json_from_response(response)
        return result if isinstance(result, dict) else {"raw": result}


register_skill(RequirementsChatSkill())
