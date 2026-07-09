# PlanOpticon Bootstrap

This is the primary conventions document. All agent shims (`CLAUDE.md`, `AGENTS.md`, `CALLIOPE.md`) point here. `AGENTS.md` is also used by OpenAI Codex.

An agent given this document and a business requirement should be able to generate correct, idiomatic code without exploring the codebase.

**Note:** This is the CLI tool repo — the only PUBLIC repo in the org. No secrets, no internal URLs, no SaaS implementation details belong here.

---

## What's Already Built

| Layer | What's there |
|-------|-------------|
| CLI | Click-based CLI, entry point `planopticon` → `video_processor.cli.commands:main`. Subcommands: `analyze`, `ingest`, `fetch`, `batch`, `query`, `agent`, `companion`, `list-models`, `doctor`, `init` |
| AI providers | 15+ providers in `video_processor/providers/` (OpenAI, Anthropic, Gemini, Ollama, Azure, Bedrock, Vertex, Mistral, Cohere, etc.) with model auto-discovery. Defaults to cheap models (Haiku, GPT-4o-mini, Gemini Flash) |
| Sources | 20+ connectors in `video_processor/sources/` (YouTube, web, GitHub, Reddit, RSS, podcasts, arXiv, S3, Google Workspace, M365, Obsidian, Notion, Zoom, Teams, Meet) |
| Knowledge graph | SQLite-backed (stdlib `sqlite3`, zero external deps) in `video_processor/integrators/`. Entity extraction with planning taxonomy (goals, requirements, risks, tasks, milestones), merge/dedup across sources |
| Video pipeline | `video_processor/pipeline.py` + `processors/`, `analyzers/`, `extractors/` — change-detection frame extraction, face filtering, diagram classification, action-item detection, checkpoint/resume |
| Planning agent | `video_processor/agent/` — 11 skills (project_plan, prd, roadmap, task_breakdown, github_integration, etc.) |
| Companion | Chat REPL (`video_processor/cli/companion.py`) with 15 slash commands, workspace auto-discovery, runtime provider/model switching |
| Exporters | `video_processor/exporters/` — Markdown docs, Obsidian, Notion, GitHub wiki, PlanOpticonExchange JSON, HTML/PDF, Mermaid |
| Auth | `video_processor/auth.py` — unified OAuth manager (Google, Dropbox, Zoom, Notion, GitHub, Microsoft) with saved-token / PKCE / API-key fallback chain |

---

## Module Structure

| Module | Purpose |
|--------|---------|
| `video_processor/cli/` | CLI commands, companion REPL, doctor, init wizard, output formatting |
| `video_processor/providers/` | AI provider implementations — `base.py` (interface), `manager.py` (selection), `discovery.py` (model auto-discovery), one file per provider |
| `video_processor/sources/` | Source connectors for fetching remote content |
| `video_processor/processors/` | Video/audio processing stages |
| `video_processor/analyzers/` | Content analysis (diagrams, actions, faces) |
| `video_processor/extractors/` | Frame/audio/entity extraction |
| `video_processor/integrators/` | Knowledge graph store, query engine, graph discovery |
| `video_processor/exporters/` | Output format writers |
| `video_processor/agent/` | Planning agent + skills |
| `video_processor/api/` | API spec / cache layer |
| `video_processor/models.py` | Pydantic data models |
| `video_processor/pipeline.py` | Main processing pipeline orchestration |
| `video_processor/exchange.py` | PlanOpticonExchange JSON interchange format |
| `video_processor/output_structure.py` | Output directory/manifest layout |

---

## Conventions

### Data Models

Pydantic v2 models (`video_processor/models.py`). Validate at boundaries — CLI input, provider responses, source payloads. Trust internal code.

### Providers

New provider = one file in `providers/` subclassing the interface in `base.py`, registered with `manager.py`/`discovery.py`. Optional heavy dependencies go behind a `pyproject.toml` extra (see `[project.optional-dependencies]`) — import inside functions/try-except, never at module top level, so the core install stays lean.

### Sources / Exporters

Same pattern as providers: one module per connector, optional deps behind extras, graceful degradation with a clear error message telling the user which extra to install.

### Knowledge Graph

SQLite via stdlib only — no ORM, no external graph dependencies. This is an architecture decision; don't add dependencies here.

### Auth

OAuth manager in `auth.py` handles all connector auth. Fallback chain: saved token → PKCE flow → API key. Never store tokens or keys in plaintext in the repo; user credentials live in the user's config dir.

### Tests

- pytest, tests in `tests/`, files `test_*.py`. Coverage is on by default (`addopts = --cov=video_processor`).
- Real SQLite in graph tests — never mock the database.
- Mock only true external boundaries (LLM APIs, network fetches). Assert on real outputs: graph DB state, generated files, manifest content.
- Every new feature and bug fix ships with tests: happy path and error path.

### Code Style

- Ruff is canonical: format + lint, line length 100, target py310 (`[tool.ruff]` in `pyproject.toml`).
- Python ≥3.10. venv mandatory — never install into system Python. Prefer `uv` for env/installs.
- No new runtime dependencies without justification — heavy/optional ones go behind extras.

---

## Adding a New Provider (example workflow)

1. Create `video_processor/providers/<name>_provider.py` subclassing the base interface.
2. Register in `manager.py` / `discovery.py`.
3. Add optional dependency extra in `pyproject.toml` if needed.
4. Add `tests/test_*` coverage — provider selection, discovery, and error path when the extra isn't installed.
5. Update README provider list.

Sources and exporters follow the same shape in their own directories.

---

## Common Commands

```bash
# Environment
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

# Run
planopticon analyze -i meeting.mp4 -o ./output
planopticon query
planopticon companion

# Quality gates (run before every PR)
ruff check video_processor tests
ruff format --check video_processor tests
pytest
```

---

## Process

Full development process, planning methodology, and quality standards: run `/primer` (CONFLICT development primer). Non-negotiables that apply here:

- Plans go on GitHub issues (ConflictHQ/PlanOpticon), never in local markdown files.
- One PR per issue. Branch naming: `feature/`, `fix/`, `chore/` + issue number.
- No rebases, no force pushes, no AI attribution in commits.
- CI green + review before merge. No TODOs or stubs in merged code.
- This repo is a submodule of the private SaaS monorepo — push this repo before pushing the parent.
