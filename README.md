# PlanOpticon

[![CI](https://github.com/ConflictHQ/PlanOpticon/actions/workflows/ci.yml/badge.svg)](https://github.com/ConflictHQ/PlanOpticon/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/planopticon)](https://pypi.org/project/planopticon/)
[![Python](https://img.shields.io/pypi/pyversions/planopticon)](https://pypi.org/project/planopticon/)
[![License](https://img.shields.io/github/license/ConflictHQ/PlanOpticon)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-planopticon.dev-blue)](https://planopticon.dev)

**AI-powered video analysis, knowledge extraction, and planning.**

PlanOpticon processes video recordings, documents, and 20+ online sources into structured knowledge graphs, then helps you plan with an AI agent and interactive companion. It auto-discovers models across 15+ AI providers, runs fully offline with Ollama, and produces rich multi-format output.

## Features

- **15+ AI providers** -- OpenAI, Anthropic, Gemini, Ollama, Azure, Together, Fireworks, Cerebras, xAI, Bedrock, Vertex, Mistral, Cohere, AI21, HuggingFace, Replicate, Qianfan, and LiteLLM. Defaults to cheap models (Haiku, GPT-4o-mini, Gemini Flash).
- **20+ source connectors** -- YouTube, web pages, GitHub, Reddit, HackerNews, RSS, podcasts, arXiv, S3, Google Workspace, Microsoft 365, Obsidian, Notion, Apple Notes, Zoom, Teams, Google Meet, and more.
- **Planning agent** -- 11 skills including project plans, PRDs, roadmaps, task breakdowns, and GitHub integration.
- **Interactive companion** -- Chat REPL with 15 slash commands, auto-discovery of workspace knowledge, and runtime provider/model switching.
- **Knowledge graphs** -- SQLite-backed (zero external deps), entity extraction with planning taxonomy (goals, requirements, risks, tasks, milestones), merge and dedup across sources.
- **Smart video analysis** -- Change-detection frame extraction, face filtering, diagram classification, action item detection, checkpoint/resume.
- **Document ingestion** -- PDF, Markdown, and plaintext pipelines feed the same knowledge graph.
- **Export everywhere** -- Markdown docs (7 types, no LLM required), Obsidian vaults, Notion markdown, GitHub wiki with push, PlanOpticonExchange JSON interchange, HTML/PDF reports, Mermaid diagrams.
- **OAuth-first auth** -- Unified OAuth manager for Google, Dropbox, Zoom, Notion, GitHub, and Microsoft with saved-token / PKCE / API-key fallback chain.
- **Batch processing** -- Process entire folders with merged knowledge graphs and cross-referencing.

## Quick Start

```bash
# Install
pip install planopticon

# Analyze a video
planopticon analyze -i meeting.mp4 -o ./output

# Ingest a document
planopticon ingest -i spec.pdf -o ./output

# Fetch from a source
planopticon fetch youtube "https://youtube.com/watch?v=..." -o ./output

# Process a folder of videos
planopticon batch -i ./recordings -o ./output --title "Weekly Meetings"

# Query the knowledge graph
planopticon query
planopticon query "entities --type technology"

# See available AI models
planopticon list-models
```

## Planning Agent

Run AI-powered planning skills against your knowledge base:

```bash
# Generate a project plan from extracted knowledge
planopticon agent "Create a project plan" --kb ./results

# Build a PRD
planopticon agent "Write a PRD for the authentication system" --kb ./results

# Break down tasks
planopticon agent "Break this into tasks and estimate effort" --kb ./results
```

11 skills: `project_plan`, `prd`, `roadmap`, `task_breakdown`, `github_integration`, `requirements_chat`, `doc_generator`, `artifact_export`, `cli_adapter`, `notes_export`, `wiki_generator`.

## Interactive Companion

A chat REPL that auto-discovers knowledge graphs, videos, and docs in your workspace:

```bash
# Launch the companion
planopticon companion
# or
planopticon --chat
```

15 slash commands: `/help`, `/status`, `/skills`, `/entities`, `/search`, `/neighbors`, `/export`, `/analyze`, `/ingest`, `/auth`, `/provider`, `/model`, `/run`, `/plan`, `/prd`, `/tasks`.

Switch providers and models at runtime, explore your knowledge graph interactively, or chat with any configured LLM.

## Source Connectors

| Category | Sources |
|----------|---------|
| Media | YouTube, Web, Podcasts, RSS |
| Code & Community | GitHub, Reddit, HackerNews, arXiv |
| Cloud Storage | S3, Google Drive, Dropbox |
| Google Workspace | Docs, Sheets, Slides (via gws CLI) |
| Microsoft 365 | SharePoint, OneDrive (via m365 CLI) |
| Notes | Obsidian, Notion, Apple Notes, OneNote, Google Keep, Logseq |
| Meetings | Zoom (OAuth), Teams, Google Meet |

## Export & Documents

Generate documents from your knowledge graph without an LLM:

```bash
planopticon export summary -o ./docs
planopticon export meeting-notes -o ./docs
planopticon export glossary -o ./docs
```

7 document types: `summary`, `meeting-notes`, `glossary`, `relationship-map`, `status-report`, `entity-index`, `csv`.

Additional export targets:
- **Obsidian** -- YAML frontmatter + wiki-links vault
- **Notion** -- Compatible markdown
- **GitHub Wiki** -- Generate and push directly
- **PlanOpticonExchange** -- Canonical JSON interchange with merge/dedup

## Local Run

PlanOpticon runs entirely offline with Ollama -- no API keys, no cloud, no cost.

> **13.2 hours of video content analyzed, knowledge-graphed, and summarized in ~25 hours of processing time, entirely on local hardware, for free.**

18 meeting recordings processed on a single machine using `llava` (vision), `qwen3:30b` (chat), and `whisper-large` (transcription via Apple Silicon GPU):

| Metric | Value |
|--------|-------|
| Recordings | 18 |
| Video duration | 13.2 hours |
| Processing time | 24.9 hours |
| Frames extracted | 1,783 |
| API calls (local) | 1,841 |
| Tokens processed | 4.87M |
| Total cost | **$0.00** |

```bash
# Fully local analysis -- no API keys needed, just Ollama running
planopticon analyze -i meeting.mp4 -o ./output \
  --provider ollama \
  --vision-model llava:latest \
  --chat-model qwen3:30b
```

## Installation

### From PyPI

```bash
pip install planopticon

# With all extras (PDF, cloud sources, GPU)
pip install planopticon[all]
```

### From Source

```bash
git clone https://github.com/ConflictHQ/PlanOpticon.git
cd PlanOpticon
pip install -e ".[dev]"
```

### Binary Download

Download standalone binaries (no Python required) from [GitHub Releases](https://github.com/ConflictHQ/PlanOpticon/releases).

### Requirements

- Python 3.10+
- FFmpeg (`brew install ffmpeg` / `apt install ffmpeg`)
- At least one API key (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY`) **or** [Ollama](https://ollama.com) running locally

## Output Structure

```
output/
├── manifest.json              # Single source of truth
├── transcript/
│   ├── transcript.json        # Full transcript with timestamps
│   ├── transcript.txt         # Plain text
│   └── transcript.srt         # Subtitles
├── frames/                    # Content frames (people filtered out)
├── diagrams/                  # Detected diagrams + mermaid code
├── captures/                  # Screengrab fallbacks
└── results/
    ├── analysis.md            # Markdown report
    ├── analysis.html          # HTML report
    ├── analysis.pdf           # PDF report
    ├── knowledge_graph.db     # SQLite knowledge graph
    ├── knowledge_graph.json   # JSON export
    ├── key_points.json        # Extracted key points
    └── action_items.json      # Tasks and follow-ups
```

## Processing Depth

| Depth | What you get |
|-------|-------------|
| `basic` | Transcription, key points, action items |
| `standard` | + Diagram extraction (10 frames), knowledge graph, full reports |
| `comprehensive` | + More frames analyzed (20), deeper extraction |

## Documentation

Full documentation at [planopticon.dev](https://planopticon.dev)

## License

MIT License -- Copyright (c) 2026 CONFLICT LLC
