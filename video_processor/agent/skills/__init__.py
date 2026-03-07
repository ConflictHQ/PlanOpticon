"""Agent skill system for PlanOpticon."""

# Import skill modules so they self-register via register_skill().
from video_processor.agent.skills import (  # noqa: F401
    artifact_export,
    cli_adapter,
    doc_generator,
    github_integration,
    prd,
    project_plan,
    requirements_chat,
    roadmap,
    task_breakdown,
)
from video_processor.agent.skills.base import (
    AgentContext,
    Artifact,
    Skill,
    get_skill,
    list_skills,
    register_skill,
)

__all__ = [
    "AgentContext",
    "Artifact",
    "Skill",
    "get_skill",
    "list_skills",
    "register_skill",
]
