# Agent API Reference

::: video_processor.agent.agent_loop

::: video_processor.agent.skills.base

::: video_processor.agent.kb_context

---

## Overview

The agent module implements a planning agent that synthesizes knowledge from processed video content into actionable artifacts such as project plans, PRDs, task breakdowns, and roadmaps. The agent operates on knowledge graphs loaded via `KBContext` and uses a skill-based architecture for extensibility.

**Key components:**

- **`PlanningAgent`** -- orchestrates skill selection and execution based on user requests
- **`AgentContext`** -- shared state passed between skills during execution
- **`Skill`** (ABC) -- base class for pluggable agent capabilities
- **`Artifact`** -- output produced by skill execution
- **`KBContext`** -- loads and merges multiple knowledge graph sources

---

## PlanningAgent

```python
from video_processor.agent.agent_loop import PlanningAgent
```

AI agent that synthesizes knowledge into planning artifacts. Uses an LLM to select which skills to execute for a given request, or falls back to keyword matching when no LLM is available.

### Constructor

```python
def __init__(self, context: AgentContext)
```

| Parameter | Type | Description |
|---|---|---|
| `context` | `AgentContext` | Shared context containing knowledge graph, query engine, and provider |

### from_kb_paths()

```python
@classmethod
def from_kb_paths(
    cls,
    kb_paths: List[Path],
    provider_manager=None,
) -> PlanningAgent
```

Factory method that creates an agent from one or more knowledge base file paths. Handles loading and merging knowledge graphs automatically.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `kb_paths` | `List[Path]` | *required* | Paths to `.db` or `.json` knowledge graph files, or directories to search |
| `provider_manager` | `ProviderManager` | `None` | LLM provider for agent operations |

**Returns:** `PlanningAgent` -- configured agent with loaded knowledge base.

```python
from pathlib import Path
from video_processor.agent.agent_loop import PlanningAgent
from video_processor.providers.manager import ProviderManager

agent = PlanningAgent.from_kb_paths(
    kb_paths=[Path("results/knowledge_graph.db")],
    provider_manager=ProviderManager(),
)
```

### execute()

```python
def execute(self, request: str) -> List[Artifact]
```

Execute a user request by selecting and running appropriate skills.

**Process:**

1. Build a context summary from the knowledge base statistics
2. Format available skills with their descriptions
3. Ask the LLM to select skills and parameters (or use keyword matching as fallback)
4. Execute selected skills in order, accumulating artifacts

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `request` | `str` | Natural language request (e.g., "Generate a project plan") |

**Returns:** `List[Artifact]` -- generated artifacts from skill execution.

**LLM mode:** The LLM receives the knowledge base summary, available skills, and user request, then returns a JSON array of `{"skill": "name", "params": {}}` objects to execute.

**Keyword fallback:** Without an LLM, skills are matched by splitting the skill name into words and checking if any appear in the request text.

```python
artifacts = agent.execute("Create a PRD and task breakdown")
for artifact in artifacts:
    print(f"--- {artifact.name} ({artifact.artifact_type}) ---")
    print(artifact.content[:500])
```

### chat()

```python
def chat(self, message: str) -> str
```

Interactive chat mode. Maintains conversation history and provides contextual responses about the loaded knowledge base.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `message` | `str` | User message |

**Returns:** `str` -- assistant response.

The chat mode provides the LLM with:

- Knowledge base statistics (entity counts, relationship counts)
- List of previously generated artifacts
- Full conversation history
- Available REPL commands (e.g., `/entities`, `/search`, `/plan`, `/export`)

**Requires** a configured `provider_manager`. Returns a static error message if no LLM is available.

```python
response = agent.chat("What technologies were discussed in the meetings?")
print(response)

response = agent.chat("Which of those have the most dependencies?")
print(response)
```

---

## AgentContext

```python
from video_processor.agent.skills.base import AgentContext
```

Shared state dataclass passed to all skills during execution. Accumulates artifacts and conversation history across the agent session.

| Field | Type | Default | Description |
|---|---|---|---|
| `knowledge_graph` | `Any` | `None` | `KnowledgeGraph` instance |
| `query_engine` | `Any` | `None` | `GraphQueryEngine` instance for querying the KG |
| `provider_manager` | `Any` | `None` | `ProviderManager` instance for LLM calls |
| `planning_entities` | `List[Any]` | `[]` | Extracted `PlanningEntity` instances |
| `user_requirements` | `Dict[str, Any]` | `{}` | User-specified requirements and constraints |
| `conversation_history` | `List[Dict[str, str]]` | `[]` | Chat message history (`role`, `content` dicts) |
| `artifacts` | `List[Artifact]` | `[]` | Previously generated artifacts |
| `config` | `Dict[str, Any]` | `{}` | Additional configuration |

```python
from video_processor.agent.skills.base import AgentContext

context = AgentContext(
    knowledge_graph=kg,
    query_engine=engine,
    provider_manager=pm,
    config={"output_format": "markdown"},
)
```

---

## Skill (ABC)

```python
from video_processor.agent.skills.base import Skill
```

Base class for agent skills. Each skill represents a discrete capability that produces an artifact from the agent context.

**Class attributes:**

| Attribute | Type | Description |
|---|---|---|
| `name` | `str` | Skill identifier (e.g., `"project_plan"`, `"prd"`) |
| `description` | `str` | Human-readable description shown to the LLM for skill selection |

### execute()

```python
@abstractmethod
def execute(self, context: AgentContext, **kwargs) -> Artifact
```

Execute this skill and return an artifact. Receives the shared agent context and any parameters selected by the LLM planner.

### can_execute()

```python
def can_execute(self, context: AgentContext) -> bool
```

Check if this skill can execute given the current context. The default implementation requires both `knowledge_graph` and `provider_manager` to be set. Override for skills with different requirements.

**Returns:** `bool`

### Implementing a custom skill

```python
from video_processor.agent.skills.base import Skill, Artifact, AgentContext, register_skill

class SummarySkill(Skill):
    name = "summary"
    description = "Generate a concise summary of the knowledge base"

    def execute(self, context: AgentContext, **kwargs) -> Artifact:
        stats = context.query_engine.stats()
        prompt = f"Summarize this knowledge base:\n{stats.to_text()}"
        content = context.provider_manager.chat(
            [{"role": "user", "content": prompt}]
        )
        return Artifact(
            name="Knowledge Base Summary",
            content=content,
            artifact_type="document",
            format="markdown",
        )

    def can_execute(self, context: AgentContext) -> bool:
        return context.query_engine is not None and context.provider_manager is not None

# Register the skill so the agent can discover it
register_skill(SummarySkill())
```

---

## Artifact

```python
from video_processor.agent.skills.base import Artifact
```

Dataclass representing the output of a skill execution.

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | *required* | Human-readable artifact name |
| `content` | `str` | *required* | Generated content (Markdown, JSON, Mermaid, etc.) |
| `artifact_type` | `str` | *required* | Type: `"project_plan"`, `"prd"`, `"roadmap"`, `"task_list"`, `"document"`, `"issues"` |
| `format` | `str` | `"markdown"` | Content format: `"markdown"`, `"json"`, `"mermaid"` |
| `metadata` | `Dict[str, Any]` | `{}` | Additional metadata |

---

## Skill Registry Functions

### register_skill()

```python
def register_skill(skill: Skill) -> None
```

Register a skill instance in the global registry. Skills must be registered before the agent can discover and execute them.

### get_skill()

```python
def get_skill(name: str) -> Optional[Skill]
```

Look up a registered skill by name.

**Returns:** `Optional[Skill]` -- the skill instance, or `None` if not found.

### list_skills()

```python
def list_skills() -> List[Skill]
```

Return all registered skill instances.

---

## KBContext

```python
from video_processor.agent.kb_context import KBContext
```

Loads and merges multiple knowledge graph sources into a unified context for agent consumption. Supports both FalkorDB (`.db`) and JSON (`.json`) formats, and can auto-discover graphs in a directory tree.

### Constructor

```python
def __init__(self)
```

Creates an empty context. Use `add_source()` to add knowledge graph paths, then `load()` to initialize.

### add_source()

```python
def add_source(self, path) -> None
```

Add a knowledge graph source.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `path` | `str \| Path` | Path to a `.db` file, `.json` file, or directory to search for knowledge graphs |

If `path` is a directory, it is searched recursively for knowledge graph files using `find_knowledge_graphs()`.

**Raises:** `FileNotFoundError` if the path does not exist.

### load()

```python
def load(self, provider_manager=None) -> KBContext
```

Load and merge all added sources into a single knowledge graph and query engine.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `provider_manager` | `ProviderManager` | `None` | LLM provider for the knowledge graph and query engine |

**Returns:** `KBContext` -- self, for method chaining.

### Properties

| Property | Type | Description |
|---|---|---|
| `knowledge_graph` | `KnowledgeGraph` | The merged knowledge graph (raises `RuntimeError` if not loaded) |
| `query_engine` | `GraphQueryEngine` | Query engine for the merged graph (raises `RuntimeError` if not loaded) |
| `sources` | `List[Path]` | List of resolved source paths |

### summary()

```python
def summary(self) -> str
```

Generate a brief text summary of the loaded knowledge base, including entity counts by type and relationship counts.

**Returns:** `str` -- multi-line summary text.

### auto_discover()

```python
@classmethod
def auto_discover(
    cls,
    start_dir: Optional[Path] = None,
    provider_manager=None,
) -> KBContext
```

Factory method that creates a `KBContext` by auto-discovering knowledge graphs near `start_dir` (defaults to current directory).

**Returns:** `KBContext` -- loaded context (may have zero sources if none found).

### Usage examples

```python
from pathlib import Path
from video_processor.agent.kb_context import KBContext

# Manual source management
kb = KBContext()
kb.add_source(Path("project_a/knowledge_graph.db"))
kb.add_source(Path("project_b/results/"))  # searches directory
kb.load(provider_manager=pm)

print(kb.summary())
# Knowledge base: 3 source(s)
#   Entities: 142
#   Relationships: 89
#   Entity types:
#     technology: 45
#     person: 23
#     concept: 74

# Auto-discover from current directory
kb = KBContext.auto_discover()

# Use with the agent
from video_processor.agent.agent_loop import PlanningAgent
from video_processor.agent.skills.base import AgentContext

context = AgentContext(
    knowledge_graph=kb.knowledge_graph,
    query_engine=kb.query_engine,
    provider_manager=pm,
)
agent = PlanningAgent(context)
```
