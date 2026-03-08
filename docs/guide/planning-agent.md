# Planning Agent

The Planning Agent is PlanOpticon's AI-powered system for synthesizing knowledge graph content into structured planning artifacts. It takes extracted entities and relationships from video analyses, document ingestions, and other sources, then uses LLM reasoning to produce project plans, PRDs, roadmaps, task breakdowns, GitHub issues, and more.

---

## How It Works

The Planning Agent operates through a three-stage pipeline:

### 1. Context Assembly

The agent gathers context from all available sources:

- **Knowledge graph** -- entity counts, types, relationships, and planning entities from the loaded KG
- **Query engine** -- used to pull stats, entity lists, and relationship data for prompt construction
- **Provider manager** -- the configured LLM provider used for generation
- **Prior artifacts** -- any artifacts already generated in the session (skills can chain off each other)
- **Conversation history** -- accumulated chat messages when running in interactive mode

This context is bundled into an `AgentContext` dataclass that is shared across all skills.

### 2. Skill Selection

When the agent receives a user request, it determines which skills to run:

**LLM-driven planning (with provider).** The agent constructs a prompt that includes the knowledge base summary, all available skill names and descriptions, and the user's request. The LLM returns a JSON array of skill names to execute in order, along with any parameters. For example, given "Create a project plan and break it into tasks," the LLM might select `["project_plan", "task_breakdown"]`.

**Keyword fallback (without provider).** If no LLM provider is available, the agent falls back to simple keyword matching. It splits each skill name on underscores and checks whether any of those words appear in the user's request. For example, the request "generate a roadmap" would match the `roadmap` skill because "roadmap" appears in both the request and the skill name.

### 3. Execution

Selected skills are executed sequentially. Each skill:

1. Checks `can_execute()` to verify the required context is available (by default, both a knowledge graph and an LLM provider must be present)
2. Pulls relevant data from the knowledge graph via the query engine
3. Constructs a detailed prompt for the LLM with extracted context
4. Calls the LLM and parses the response
5. Returns an `Artifact` object containing the generated content

Each artifact is appended to `context.artifacts`, making it available to subsequent skills. This enables chaining -- for example, `task_breakdown` can feed into `github_issues`.

---

## AgentContext

The `AgentContext` dataclass is the shared state object that connects all components of the planning agent system.

```python
@dataclass
class AgentContext:
    knowledge_graph: Any = None       # KnowledgeGraph instance
    query_engine: Any = None          # GraphQueryEngine instance
    provider_manager: Any = None      # ProviderManager instance
    planning_entities: List[Any] = field(default_factory=list)
    user_requirements: Dict[str, Any] = field(default_factory=dict)
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    artifacts: List[Artifact] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
```

| Field | Purpose |
|---|---|
| `knowledge_graph` | The loaded `KnowledgeGraph` instance; provides access to entities, relationships, and graph operations |
| `query_engine` | A `GraphQueryEngine` for running structured queries (stats, entities, neighbors, relationships) |
| `provider_manager` | The `ProviderManager` that handles LLM API calls across providers |
| `planning_entities` | Entities classified into the planning taxonomy (goals, requirements, risks, etc.) |
| `user_requirements` | Structured requirements gathered from the `requirements_chat` skill |
| `conversation_history` | Accumulated chat messages for interactive sessions |
| `artifacts` | All artifacts generated during the session, enabling skill chaining |
| `config` | Arbitrary configuration overrides |

---

## Artifacts

Every skill returns an `Artifact` dataclass:

```python
@dataclass
class Artifact:
    name: str              # Human-readable name (e.g., "Project Plan")
    content: str           # The generated content (markdown, JSON, etc.)
    artifact_type: str     # Type identifier: "project_plan", "prd", "roadmap", etc.
    format: str = "markdown"  # Content format: "markdown", "json", "mermaid"
    metadata: Dict[str, Any] = field(default_factory=dict)
```

Artifacts are the currency of the agent system. They can be:

- Displayed directly in the Companion REPL
- Exported to disk via the `artifact_export` skill
- Pushed to external tools via the `cli_adapter` skill
- Chained into other skills (e.g., task breakdown feeds into GitHub issues)

---

## Skills Reference

The agent ships with 11 built-in skills. Each skill is a class that extends `Skill` and self-registers at import time via `register_skill()`.

### project_plan

**Description:** Generate a structured project plan from knowledge graph.

Pulls the full knowledge graph context (stats, entities, relationships, and planning entities grouped by type) and asks the LLM to produce a comprehensive project plan with:

1. Executive Summary
2. Goals and Objectives
3. Scope
4. Phases and Milestones
5. Resource Requirements
6. Risks and Mitigations
7. Success Criteria

**Artifact type:** `project_plan` | **Format:** markdown

### prd

**Description:** Generate a product requirements document (PRD) / feature spec.

Filters planning entities to those of type `requirement`, `feature`, and `constraint`, then asks the LLM to generate a PRD with:

1. Problem Statement
2. User Stories
3. Functional Requirements
4. Non-Functional Requirements
5. Acceptance Criteria
6. Out of Scope

If no pre-filtered entities match, the LLM derives requirements from the full knowledge graph context.

**Artifact type:** `prd` | **Format:** markdown

### roadmap

**Description:** Generate a product/project roadmap.

Focuses on planning entities of type `milestone`, `feature`, and `dependency`. Asks the LLM to produce a roadmap with:

1. Vision and Strategy
2. Phases (with timeline estimates)
3. Key Dependencies
4. A Mermaid Gantt chart summarizing the timeline

**Artifact type:** `roadmap` | **Format:** markdown

### task_breakdown

**Description:** Break down goals into tasks with dependencies.

Focuses on planning entities of type `goal`, `feature`, and `milestone`. Returns a JSON array of task objects, each containing:

| Field | Type | Description |
|---|---|---|
| `id` | string | Task identifier (e.g., "T1", "T2") |
| `title` | string | Short task title |
| `description` | string | Detailed description |
| `depends_on` | list | IDs of prerequisite tasks |
| `priority` | string | `high`, `medium`, or `low` |
| `estimate` | string | Effort estimate (e.g., "2d", "1w") |
| `assignee_role` | string | Role needed to perform the task |

**Artifact type:** `task_list` | **Format:** json

### github_issues

**Description:** Generate GitHub issues from task breakdown.

Converts tasks into GitHub-ready issue objects. If a `task_list` artifact exists in the context, it is used as input. Otherwise, minimal issues are generated from the planning entities directly.

Each issue includes a formatted body with description, priority, estimate, and dependencies, plus labels derived from the task priority.

The skill also provides a `push_to_github(issues_json, repo)` function that shells out to the `gh` CLI to create actual issues. This is used by the `cli_adapter` skill.

**Artifact type:** `issues` | **Format:** json

### requirements_chat

**Description:** Interactive requirements gathering via guided questions.

Generates a structured requirements questionnaire based on the knowledge graph context. The questionnaire contains 8-12 targeted questions, each with:

| Field | Type | Description |
|---|---|---|
| `id` | string | Question identifier (e.g., "Q1") |
| `category` | string | `goals`, `constraints`, `priorities`, or `scope` |
| `question` | string | The question text |
| `context` | string | Why this question matters |

The skill also provides a `gather_requirements(context, answers)` method that takes the completed Q&A and synthesizes structured requirements (goals, constraints, priorities, scope).

**Artifact type:** `requirements` | **Format:** json

### doc_generator

**Description:** Generate technical documentation, ADRs, or meeting notes.

Supports three document types, selected via the `doc_type` parameter:

| `doc_type` | Output Structure |
|---|---|
| `technical_doc` (default) | Overview, Architecture, Components and Interfaces, Data Flow, Deployment and Configuration, API Reference |
| `adr` | Title, Status (Proposed), Context, Decision, Consequences, Alternatives Considered |
| `meeting_notes` | Meeting Summary, Key Discussion Points, Decisions Made, Action Items (with owners), Open Questions, Next Steps |

**Artifact type:** `document` | **Format:** markdown

### artifact_export

**Description:** Export artifacts in agent-ready formats.

Writes all artifacts accumulated in the context to a directory structure. Each artifact is written to a file based on its type:

| Artifact Type | Filename |
|---|---|
| `project_plan` | `project_plan.md` |
| `prd` | `prd.md` |
| `roadmap` | `roadmap.md` |
| `task_list` | `tasks.json` |
| `issues` | `issues.json` |
| `requirements` | `requirements.json` |
| `document` | `docs/<name>.md` |

A `manifest.json` is written alongside, listing all exported files with their names, types, and formats.

**Artifact type:** `export_manifest` | **Format:** json

Accepts an `output_dir` parameter (defaults to `plan/`).

### cli_adapter

**Description:** Push artifacts to external tools via their CLIs.

Converts artifacts into CLI commands for external project management tools. Supported tools:

| Tool | CLI | Example Command |
|---|---|---|
| `github` | `gh` | `gh issue create --title "..." --body "..." --label "..."` |
| `jira` | `jira` | `jira issue create --summary "..." --description "..."` |
| `linear` | `linear` | `linear issue create --title "..." --description "..."` |

The skill checks whether the target CLI is available on the system and includes that status in the output. Commands are generated in dry-run mode by default.

**Artifact type:** `cli_commands` | **Format:** json

### notes_export

**Description:** Export knowledge graph as structured notes (Obsidian, Notion).

Exports the entire knowledge graph as a collection of markdown files optimized for a specific note-taking platform. Accepts a `format` parameter:

**Obsidian format** creates:

- One `.md` file per entity with YAML frontmatter, tags, and `[[wiki-links]]`
- An `_Index.md` Map of Content grouping entities by type
- Tag pages for each entity type
- Artifact notes for any generated artifacts

**Notion format** creates:

- One `.md` file per entity with Notion-style callout blocks and relationship tables
- An `entities_database.csv` for bulk import into a Notion database
- An `Overview.md` page with stats and entity listings
- Artifact pages

**Artifact type:** `notes_export` | **Format:** markdown

### wiki_generator

**Description:** Generate a GitHub wiki from knowledge graph and artifacts.

Generates a complete GitHub wiki structure as a dictionary of page names to markdown content. Creates:

- **Home** page with entity type counts and links
- **_Sidebar** navigation with entity types and artifacts
- **Type index pages** with tables of entities per type
- **Individual entity pages** with descriptions, outgoing/incoming relationships, and source occurrences
- **Artifact pages** for any generated planning artifacts

The skill also provides standalone functions `write_wiki(pages, output_dir)` to write pages to disk and `push_wiki(wiki_dir, repo)` to push directly to a GitHub wiki repository.

**Artifact type:** `wiki` | **Format:** markdown

---

## CLI Usage

### One-shot execution

Run the agent with a request string. The agent selects and executes appropriate skills automatically.

```bash
# Generate a project plan
planopticon agent "Create a project plan" --kb ./results

# Generate a PRD
planopticon agent "Write a PRD for the authentication system" --kb ./results

# Break down into tasks
planopticon agent "Break this into tasks and estimate effort" --kb ./results
```

### Export artifacts to disk

Use `--export` to write generated artifacts to a directory:

```bash
planopticon agent "Create a full project plan with tasks" --kb ./results --export ./output
```

### Interactive mode

Use `-I` for a multi-turn session where you can issue multiple requests:

```bash
planopticon agent -I --kb ./results
```

In interactive mode, the agent supports:

- Free-text requests (executed via LLM skill selection)
- `/plan` -- shortcut to generate a project plan
- `/skills` -- list available skills
- `quit`, `exit`, `q` -- end the session

### Provider and model options

```bash
# Use a specific provider
planopticon agent "Create a roadmap" --kb ./results -p anthropic

# Use a specific model
planopticon agent "Generate a PRD" --kb ./results --chat-model gpt-4o
```

### Auto-discovery

If `--kb` is not specified, the agent uses `KBContext.auto_discover()` to find knowledge graphs in the workspace.

---

## Using Skills from the Companion REPL

The Companion REPL provides direct access to agent skills through slash commands. See the [Companion guide](companion.md) for full details.

| Companion Command | Skill Executed |
|---|---|
| `/plan` | `project_plan` |
| `/prd` | `prd` |
| `/tasks` | `task_breakdown` |
| `/run SKILL_NAME` | Any registered skill by name |

When executed from the Companion, skills use the same `AgentContext` that powers the chat mode. This means:

- The knowledge graph loaded at startup is automatically available
- The active LLM provider (set via `/provider` or `/model`) is used for generation
- Generated artifacts accumulate across the session, enabling chaining

---

## Example Workflows

### From video to project plan

```bash
# 1. Analyze a video
planopticon analyze -i sprint-review.mp4 -o results/

# 2. Launch the agent with the results
planopticon agent "Create a comprehensive project plan with tasks and a roadmap" \
    --kb results/ --export plan/

# 3. Review the generated artifacts
ls plan/
# project_plan.md  roadmap.md  tasks.json  manifest.json
```

### Interactive planning session

```bash
$ planopticon companion --kb ./results

planopticon> /status
Workspace status:
  KG: knowledge_graph.db (58 entities, 124 relationships)
  ...

planopticon> What are the main goals discussed?
Based on the knowledge graph, the main goals are...

planopticon> /plan
--- Project Plan (project_plan) ---
...

planopticon> /tasks
--- Task Breakdown (task_list) ---
...

planopticon> /run github_issues
--- GitHub Issues (issues) ---
[
  {"title": "Set up authentication service", ...},
  ...
]

planopticon> /run artifact_export
--- Export Manifest (export_manifest) ---
{
  "artifact_count": 3,
  "output_dir": "plan",
  "files": [...]
}
```

### Skill chaining

Skills that produce artifacts make them available to subsequent skills automatically:

1. `/tasks` generates a `task_list` artifact
2. `/run github_issues` detects the existing `task_list` artifact and converts its tasks into GitHub issues
3. `/run cli_adapter` takes the most recent artifact and generates `gh issue create` commands
4. `/run artifact_export` writes all accumulated artifacts to disk with a manifest

This chaining works both in the Companion REPL and in one-shot agent execution, since the `AgentContext.artifacts` list persists for the duration of the session.
