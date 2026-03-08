# Interactive Companion REPL

The PlanOpticon Companion is an interactive Read-Eval-Print Loop (REPL) that provides a conversational interface to PlanOpticon's full feature set. It combines workspace awareness, knowledge graph querying, LLM-powered chat, and planning agent skills into a single session.

Use the Companion when you want to explore a knowledge graph interactively, ask natural-language questions about extracted content, generate planning artifacts on the fly, or switch between providers and models without restarting.

---

## Launching the Companion

There are three equivalent ways to start the Companion.

### As a subcommand

```bash
planopticon companion
```

### With the `--chat` / `-C` flag

```bash
planopticon --chat
planopticon -C
```

These flags launch the Companion directly from the top-level CLI, without invoking a subcommand.

### With options

The `companion` subcommand accepts options for specifying knowledge base paths, LLM provider, and model:

```bash
# Point at a specific knowledge base
planopticon companion --kb ./results

# Use a specific provider
planopticon companion -p anthropic

# Use a specific model
planopticon companion --chat-model gpt-4o

# Combine options
planopticon companion --kb ./results -p openai --chat-model gpt-4o
```

| Option | Description |
|---|---|
| `--kb PATH` | Path to a knowledge graph file or directory (repeatable) |
| `-p, --provider NAME` | LLM provider: `auto`, `openai`, `anthropic`, `gemini`, `ollama`, `azure`, `together`, `fireworks`, `cerebras`, `xai` |
| `--chat-model NAME` | Override the default chat model for the selected provider |

---

## Auto-discovery

On startup, the Companion automatically scans the workspace for relevant files:

**Knowledge graphs.** The Companion uses `find_nearest_graph()` to locate the closest `knowledge_graph.db` or `knowledge_graph.json` file. It searches the current directory, common output subdirectories (`results/`, `output/`, `knowledge-base/`), recursively downward (up to 4 levels), and upward through parent directories. SQLite `.db` files are preferred over `.json` files.

**Videos.** The current directory is scanned for files with `.mp4`, `.mkv`, and `.webm` extensions.

**Documents.** The current directory is scanned for files with `.md`, `.pdf`, and `.docx` extensions.

**LLM provider.** If `--provider` is set to `auto` (the default), the Companion attempts to initialise a provider using any available API key in the environment (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, etc.).

All discovered context is displayed in the welcome banner:

```
  PlanOpticon Companion
  Interactive planning REPL

  Knowledge graph: knowledge_graph.db  (42 entities, 87 relationships)
  Videos: meeting-2024-01-15.mp4, sprint-review.mp4
  Docs: requirements.md, architecture.pdf
  LLM provider: openai (model: gpt-4o)

  Type /help for commands, or ask a question.
```

If no knowledge graph is found, the banner shows "No knowledge graph loaded." Commands that require a KG will return an appropriate message rather than failing silently.

---

## Slash Commands

The Companion supports 18 slash commands. Type `/help` at the prompt to see the full list.

### /help

Display all available commands with brief descriptions.

```
planopticon> /help
Available commands:
  /help                  Show this help
  /status                Workspace status
  /skills                List available skills
  /entities [--type T]   List KG entities
  /search TERM           Search entities by name
  /neighbors ENTITY      Show entity relationships
  /export FORMAT         Export KG (markdown, obsidian, notion, csv)
  /analyze PATH          Analyze a video/doc
  /ingest PATH           Ingest a file into the KG
  /auth SERVICE          Authenticate with a cloud service
  /provider [NAME]       List or switch LLM provider
  /model [NAME]          Show or switch chat model
  /run SKILL             Run a skill by name
  /plan                  Run project_plan skill
  /prd                   Run PRD skill
  /tasks                 Run task_breakdown skill
  /quit, /exit           Exit companion

Any other input is sent to the chat agent (requires LLM).
```

### /status

Show a summary of the current workspace state: loaded knowledge graph (with entity and relationship counts, broken down by entity type), number of discovered videos and documents, and whether an LLM provider is active.

```
planopticon> /status
Workspace status:
  KG: /home/user/project/results/knowledge_graph.db (42 entities, 87 relationships)
    technology: 15
    person: 12
    concept: 10
    organization: 5
  Videos: 2 found
  Docs: 3 found
  Provider: active
```

### /skills

List all registered planning agent skills with their names and descriptions. These are the skills that can be invoked via `/run`.

```
planopticon> /skills
Available skills:
  project_plan: Generate a structured project plan from knowledge graph
  prd: Generate a product requirements document (PRD) / feature spec
  roadmap: Generate a product/project roadmap
  task_breakdown: Break down goals into tasks with dependencies
  github_issues: Generate GitHub issues from task breakdown
  requirements_chat: Interactive requirements gathering via guided questions
  doc_generator: Generate technical documentation, ADRs, or meeting notes
  artifact_export: Export artifacts in agent-ready formats
  cli_adapter: Push artifacts to external tools via their CLIs
  notes_export: Export knowledge graph as structured notes (Obsidian, Notion)
  wiki_generator: Generate a GitHub wiki from knowledge graph and artifacts
```

### /entities [--type TYPE]

List entities from the loaded knowledge graph. Optionally filter by entity type.

```
planopticon> /entities
Found 42 entities
  [technology] Python -- General-purpose programming language
  [person] Alice -- Lead engineer on the project
  [concept] Microservices -- Architectural pattern discussed
  ...

planopticon> /entities --type person
Found 12 entities
  [person] Alice -- Lead engineer on the project
  [person] Bob -- Product manager
  ...
```

!!! note
    This command requires a loaded knowledge graph. If none is loaded, it returns "No knowledge graph loaded."

### /search TERM

Search entities by name substring (case-insensitive).

```
planopticon> /search python
Found 3 entities
  [technology] Python -- General-purpose programming language
  [technology] Python Flask -- Web framework for Python
  [concept] Python packaging -- Discussion of pip and packaging tools
```

### /neighbors ENTITY

Show all entities and relationships connected to a given entity. This performs a breadth-first traversal (depth 1) from the named entity.

```
planopticon> /neighbors Alice
Found 4 entities and 5 relationships
  [person] Alice -- Lead engineer on the project
  [technology] Python -- General-purpose programming language
  [organization] Acme Corp -- Employer
  [concept] Authentication -- Auth system design
  Alice --[works_with]--> Python
  Alice --[employed_by]--> Acme Corp
  Alice --[proposed]--> Authentication
  Bob --[collaborates_with]--> Alice
  Authentication --[discussed_by]--> Alice
```

### /export FORMAT

Request an export of the knowledge graph. Supported formats: `markdown`, `obsidian`, `notion`, `csv`. This command prints the equivalent CLI command to run.

```
planopticon> /export obsidian
Export 'obsidian' requested. Use the CLI command:
  planopticon export obsidian /home/user/project/results/knowledge_graph.db
```

### /analyze PATH

Request analysis of a video or document file. Validates the file exists and prints the equivalent CLI command.

```
planopticon> /analyze meeting.mp4
Analyze requested for meeting.mp4. Use the CLI:
  planopticon analyze -i /home/user/project/meeting.mp4
```

### /ingest PATH

Request ingestion of a file into the knowledge graph. Validates the file exists and prints the equivalent CLI command.

```
planopticon> /ingest notes.md
Ingest requested for notes.md. Use the CLI:
  planopticon ingest /home/user/project/notes.md
```

### /auth [SERVICE]

Authenticate with a cloud service. When called without arguments, lists all available services. When called with a service name, triggers the authentication flow.

```
planopticon> /auth
Usage: /auth SERVICE
Available: dropbox, github, google, microsoft, notion, zoom

planopticon> /auth zoom
Zoom authenticated (oauth)
```

### /provider [NAME]

List available LLM providers and their status, or switch to a different provider.

When called without arguments (or with `list`), shows all known providers with their availability status:

- **ready** -- API key found in environment
- **local** -- runs locally (Ollama)
- **no key** -- no API key configured

The currently active provider is marked.

```
planopticon> /provider
Available providers:
  openai: ready (active)
  anthropic: ready
  gemini: no key
  ollama: local
  azure: no key
  together: no key
  fireworks: no key
  cerebras: no key
  xai: no key

Current: openai
```

To switch providers at runtime:

```
planopticon> /provider anthropic
Switched to provider: anthropic
```

Switching the provider reinitialises the provider manager and the planning agent. The chat model is reset to the provider's default. If initialisation fails, an error message is shown.

### /model [NAME]

Show the current chat model, or switch to a different one.

```
planopticon> /model
Current model: default
Usage: /model MODEL_NAME

planopticon> /model claude-sonnet-4-20250514
Switched to model: claude-sonnet-4-20250514
```

Switching the model reinitialises both the provider manager and the planning agent.

### /run SKILL

Run any registered skill by name. The skill receives the current agent context (knowledge graph, query engine, provider, and any previously generated artifacts) and returns an artifact.

```
planopticon> /run roadmap
--- Roadmap (roadmap) ---
# Roadmap

## Vision & Strategy
...
```

If the skill cannot execute (missing KG or provider), an error message is returned. Use `/skills` to see all available skill names.

### /plan

Shortcut for `/run project_plan`. Generates a structured project plan from the loaded knowledge graph.

```
planopticon> /plan
--- Project Plan (project_plan) ---
# Project Plan

## Executive Summary
...
```

### /prd

Shortcut for `/run prd`. Generates a product requirements document.

```
planopticon> /prd
--- Product Requirements Document (prd) ---
# Product Requirements Document

## Problem Statement
...
```

### /tasks

Shortcut for `/run task_breakdown`. Breaks goals and features into tasks with dependencies, priorities, and effort estimates. The output is JSON.

```
planopticon> /tasks
--- Task Breakdown (task_list) ---
[
  {
    "id": "T1",
    "title": "Set up authentication service",
    "description": "Implement OAuth2 flow with JWT tokens",
    "depends_on": [],
    "priority": "high",
    "estimate": "1w",
    "assignee_role": "backend engineer"
  },
  ...
]
```

### /quit and /exit

Exit the Companion REPL.

```
planopticon> /quit
Bye.
```

---

## Exiting the Companion

In addition to `/quit` and `/exit`, you can exit by:

- Typing `quit`, `exit`, `bye`, or `q` as bare words (without the `/` prefix)
- Pressing `Ctrl+C` or `Ctrl+D`

All of these end the session with a "Bye." message.

---

## Chat Mode

Any input that does not start with `/` and is not a bare exit word is sent to the chat agent as a natural-language message. This requires a configured LLM provider.

```
planopticon> What technologies were discussed in the meeting?
Based on the knowledge graph, the following technologies were discussed:

1. **Python** -- mentioned in the context of backend development
2. **React** -- proposed for the frontend redesign
3. **PostgreSQL** -- discussed as the primary database
...
```

The chat agent maintains conversation history across the session. It has full awareness of:

- The loaded knowledge graph (entity and relationship counts, types)
- Any artifacts generated during the session (via `/plan`, `/prd`, `/tasks`, `/run`)
- All available slash commands (which it may suggest when relevant)
- The full PlanOpticon CLI command set

If no LLM provider is configured, chat mode returns an error with instructions:

```
planopticon> What was discussed?
Chat requires an LLM provider. Set one of:
  OPENAI_API_KEY
  ANTHROPIC_API_KEY
  GEMINI_API_KEY
Or pass --provider / --chat-model.
```

---

## Runtime Provider and Model Switching

One of the Companion's key features is the ability to switch LLM providers and models without restarting the session. This is useful for:

- Comparing outputs across different models
- Falling back to a local model (Ollama) when API keys expire
- Using a cheaper model for exploratory queries and a more capable one for artifact generation

When you switch providers or models via `/provider` or `/model`, the Companion:

1. Updates the internal provider name and/or model name
2. Reinitialises the `ProviderManager`
3. Reinitialises the `PlanningAgent` with a fresh `AgentContext` that retains the loaded knowledge graph and query engine

Conversation history is preserved across provider switches.

---

## Example Session

The following walkthrough shows a typical Companion session, from launch through exploration to artifact generation.

```bash
$ planopticon companion --kb ./results
```

```
  PlanOpticon Companion
  Interactive planning REPL

  Knowledge graph: knowledge_graph.db  (58 entities, 124 relationships)
  Videos: sprint-review-2024-03.mp4
  Docs: architecture.md, requirements.pdf
  LLM provider: openai (model: default)

  Type /help for commands, or ask a question.

planopticon> /status
Workspace status:
  KG: /home/user/project/results/knowledge_graph.db (58 entities, 124 relationships)
    technology: 20
    person: 15
    concept: 13
    organization: 8
    time: 2
  Videos: 1 found
  Docs: 2 found
  Provider: active

planopticon> /entities --type person
Found 15 entities
  [person] Alice -- Lead architect
  [person] Bob -- Product manager
  [person] Carol -- Frontend lead
  ...

planopticon> /neighbors Alice
Found 6 entities and 8 relationships
  [person] Alice -- Lead architect
  [technology] Kubernetes -- Container orchestration platform
  [concept] Microservices -- Proposed architecture pattern
  ...
  Alice --[proposed]--> Microservices
  Alice --[expert_in]--> Kubernetes
  ...

planopticon> What were the main decisions made in the sprint review?
Based on the knowledge graph, the sprint review covered several key decisions:

1. **Adopt microservices architecture** -- Alice proposed and the team agreed
   to move from the monolith to a microservices pattern.
2. **Use Kubernetes for orchestration** -- Selected over Docker Swarm.
3. **Prioritize authentication module** -- Bob identified this as the highest
   priority for the next sprint.

planopticon> /provider anthropic
Switched to provider: anthropic

planopticon> /model claude-sonnet-4-20250514
Switched to model: claude-sonnet-4-20250514

planopticon> /plan
--- Project Plan (project_plan) ---
# Project Plan

## Executive Summary
This project plan outlines the migration from a monolithic architecture
to a microservices-based system, as discussed in the sprint review...

## Goals & Objectives
...

planopticon> /tasks
--- Task Breakdown (task_list) ---
[
  {
    "id": "T1",
    "title": "Design service boundaries",
    "description": "Define microservice boundaries based on domain analysis",
    "depends_on": [],
    "priority": "high",
    "estimate": "3d",
    "assignee_role": "architect"
  },
  ...
]

planopticon> /export obsidian
Export 'obsidian' requested. Use the CLI command:
  planopticon export obsidian /home/user/project/results/knowledge_graph.db

planopticon> quit
Bye.
```
