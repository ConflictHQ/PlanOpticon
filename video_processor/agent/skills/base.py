"""Skill interface for the PlanOpticon planning agent."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Artifact:
    """Output from a skill execution."""

    name: str
    content: str  # The generated content (markdown, json, etc.)
    artifact_type: str  # "project_plan", "prd", "roadmap", "task_list", "document", "issues"
    format: str = "markdown"  # "markdown", "json", "mermaid"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentContext:
    """Shared context for agent skills."""

    knowledge_graph: Any = None  # KnowledgeGraph instance
    query_engine: Any = None  # GraphQueryEngine instance
    provider_manager: Any = None  # ProviderManager instance
    planning_entities: List[Any] = field(default_factory=list)
    user_requirements: Dict[str, Any] = field(default_factory=dict)
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    artifacts: List[Artifact] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)


class Skill(ABC):
    """Base class for agent skills."""

    name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, context: AgentContext, **kwargs) -> Artifact:
        """Execute this skill and return an artifact."""
        ...

    def can_execute(self, context: AgentContext) -> bool:
        """Check if this skill can execute given the current context."""
        return context.knowledge_graph is not None and context.provider_manager is not None


# Skill registry
_skills: Dict[str, "Skill"] = {}


def register_skill(skill: "Skill") -> None:
    """Register a skill instance in the global registry."""
    _skills[skill.name] = skill


def get_skill(name: str) -> Optional["Skill"]:
    """Look up a skill by name."""
    return _skills.get(name)


def list_skills() -> List["Skill"]:
    """Return all registered skills."""
    return list(_skills.values())
