"""Planning agent loop for synthesizing knowledge into artifacts."""

import logging
from pathlib import Path
from typing import List

from video_processor.agent.kb_context import KBContext
from video_processor.agent.skills.base import (
    AgentContext,
    Artifact,
    get_skill,
    list_skills,
)

logger = logging.getLogger(__name__)


class PlanningAgent:
    """AI agent that synthesizes knowledge into planning artifacts."""

    def __init__(self, context: AgentContext):
        self.context = context

    @classmethod
    def from_kb_paths(cls, kb_paths: List[Path], provider_manager=None) -> "PlanningAgent":
        """Create an agent from knowledge base paths."""
        kb = KBContext()
        for path in kb_paths:
            kb.add_source(path)
        kb.load(provider_manager=provider_manager)

        context = AgentContext(
            knowledge_graph=kb.knowledge_graph,
            query_engine=kb.query_engine,
            provider_manager=provider_manager,
        )
        return cls(context)

    def execute(self, request: str) -> List[Artifact]:
        """Execute a user request by selecting and running appropriate skills."""
        # Step 1: Build context summary for LLM
        kb_summary = ""
        if self.context.query_engine:
            stats = self.context.query_engine.stats()
            kb_summary = stats.to_text()

        available_skills = list_skills()
        skill_descriptions = "\n".join(f"- {s.name}: {s.description}" for s in available_skills)

        # Step 2: Ask LLM to select skills
        plan_prompt = (
            "You are a planning agent. Given a user request and available skills, "
            "select which skills to execute and in what order.\n\n"
            f"Knowledge base:\n{kb_summary}\n\n"
            f"Available skills:\n{skill_descriptions}\n\n"
            f"User request: {request}\n\n"
            "Return a JSON array of skill names to execute in order:\n"
            '[{"skill": "skill_name", "params": {}}]\n'
            "Return ONLY the JSON array."
        )

        if not self.context.provider_manager:
            # No LLM -- try to match skills by keyword
            return self._keyword_match_execute(request)

        raw = self.context.provider_manager.chat(
            [{"role": "user", "content": plan_prompt}],
            max_tokens=512,
            temperature=0.1,
        )

        from video_processor.utils.json_parsing import parse_json_from_response

        plan = parse_json_from_response(raw)

        artifacts = []
        if isinstance(plan, list):
            for step in plan:
                if isinstance(step, dict) and "skill" in step:
                    skill = get_skill(step["skill"])
                    if skill and skill.can_execute(self.context):
                        params = step.get("params", {})
                        artifact = skill.execute(self.context, **params)
                        artifacts.append(artifact)
                        self.context.artifacts.append(artifact)

        return artifacts

    def _keyword_match_execute(self, request: str) -> List[Artifact]:
        """Fallback: match skills by keywords in the request."""
        request_lower = request.lower()
        artifacts = []
        for skill in list_skills():
            # Simple keyword matching
            skill_words = skill.name.replace("_", " ").split()
            if any(word in request_lower for word in skill_words):
                if skill.can_execute(self.context):
                    artifact = skill.execute(self.context)
                    artifacts.append(artifact)
                    self.context.artifacts.append(artifact)
        return artifacts

    def chat(self, message: str) -> str:
        """Interactive chat -- accumulate context and answer questions."""
        self.context.conversation_history.append({"role": "user", "content": message})

        if not self.context.provider_manager:
            return "Agent requires a configured LLM provider for chat mode."

        # Build system context
        kb_summary = ""
        if self.context.query_engine:
            stats = self.context.query_engine.stats()
            kb_summary = f"\n\nKnowledge base:\n{stats.to_text()}"

        artifacts_summary = ""
        if self.context.artifacts:
            artifacts_summary = "\n\nGenerated artifacts:\n" + "\n".join(
                f"- {a.name} ({a.artifact_type})" for a in self.context.artifacts
            )

        system_msg = (
            "You are PlanOpticon, an AI planning companion built into the PlanOpticon CLI. "
            "PlanOpticon is a video analysis and knowledge extraction tool that processes "
            "recordings into structured knowledge graphs.\n\n"
            "You are running inside the interactive companion REPL. The user can use these "
            "built-in commands (suggest them when relevant):\n"
            "  /status - Show workspace status (loaded KG, videos, docs)\n"
            "  /entities [--type T] - List knowledge graph entities\n"
            "  /search TERM - Search entities by name\n"
            "  /neighbors ENTITY - Show entity relationships\n"
            "  /export FORMAT - Export KG (markdown, obsidian, notion, csv)\n"
            "  /analyze PATH - Analyze a video or document\n"
            "  /ingest PATH - Ingest a file into the knowledge graph\n"
            "  /auth SERVICE - Authenticate with a service "
            "(zoom, google, microsoft, notion, dropbox, github)\n"
            "  /provider [NAME] - List or switch LLM provider\n"
            "  /model [NAME] - Show or switch chat model\n"
            "  /plan - Generate a project plan\n"
            "  /prd - Generate a PRD\n"
            "  /tasks - Generate a task breakdown\n\n"
            "PlanOpticon CLI commands the user can run outside the REPL:\n"
            "  planopticon auth zoom|google|microsoft - Authenticate with cloud services\n"
            "  planopticon recordings zoom-list|teams-list|meet-list - List cloud recordings\n"
            "  planopticon analyze -i VIDEO - Analyze a video file\n"
            "  planopticon query - Query the knowledge graph\n"
            "  planopticon export FORMAT PATH - Export knowledge graph\n\n"
            f"{kb_summary}{artifacts_summary}\n\n"
            "Help the user with their planning tasks. When they ask about capabilities, "
            "refer them to the appropriate built-in commands. Ask clarifying questions "
            "to gather requirements. When ready, suggest using specific skills or commands "
            "to generate artifacts."
        )

        messages = [{"role": "system", "content": system_msg}] + self.context.conversation_history

        response = self.context.provider_manager.chat(messages, max_tokens=2048, temperature=0.5)
        self.context.conversation_history.append({"role": "assistant", "content": response})
        return response
