# PlanOpticon

**AI-powered video analysis, knowledge extraction, and planning.**

PlanOpticon processes video recordings and documents into structured knowledge — transcripts, diagrams, action items, key points, and knowledge graphs. It connects to 20+ source platforms, auto-discovers available models across multiple AI providers, and produces rich multi-format output with an interactive companion REPL and planning agent.

---

## Features

- **Multi-provider AI** — Automatically discovers and routes to the best available model across OpenAI, Anthropic, Google Gemini, and more
- **Planning agent** — Agentic analysis that adaptively adjusts depth, focus, and strategy based on content
- **Companion REPL** — Interactive chat interface for exploring your knowledge base conversationally
- **20+ source connectors** — Google Workspace, Microsoft 365, Zoom, Teams, Meet, Notion, GitHub, YouTube, Obsidian, Apple Notes, and more
- **Document export** — Export knowledge to Markdown, Obsidian, Notion, and exchange formats
- **OAuth authentication** — Built-in `planopticon auth` for Google, Dropbox, Zoom, Notion, GitHub, and Microsoft
- **Smart frame extraction** — Change detection for transitions + periodic capture (every 30s) for slow-evolving content like document scrolling
- **People frame filtering** — OpenCV face detection removes webcam/video conference frames, keeping only shared content (slides, documents, screen shares)
- **Diagram extraction** — Vision model-based classification detects flowcharts, architecture diagrams, charts, and whiteboards
- **Knowledge graphs** — Extracts entities and relationships, builds and merges knowledge graphs across videos
- **Action item detection** — Finds commitments, tasks, and follow-ups with assignees and deadlines
- **Batch processing** — Process entire folders of videos with merged knowledge graphs and cross-referencing
- **Rich output** — Markdown, HTML, PDF, Mermaid diagrams, SVG/PNG renderings, JSON manifests
- **Cloud sources** — Fetch videos from Google Drive, Dropbox, and many more cloud platforms
- **Checkpoint/resume** — Pipeline resumes from where it left off if interrupted — no wasted work
- **Screengrab fallback** — When extraction isn't perfect, captures frames with captions — something is always better than nothing

## Quick Start

```bash
# Install from PyPI
pip install planopticon

# Analyze a single video
planopticon analyze -i meeting.mp4 -o ./output

# Ingest documents and build a knowledge graph
planopticon ingest ./notes/ --output ./kb --recursive

# Chat with your knowledge base
planopticon companion --kb ./kb

# Run the planning agent interactively
planopticon agent --kb ./kb --interactive

# Query the knowledge graph
planopticon query stats

# Export to Obsidian
planopticon export obsidian --input ./kb --output ./vault

# Process a folder of videos
planopticon batch -i ./recordings -o ./output --title "Weekly Meetings"

# See available AI models
planopticon list-models
```

## Installation

=== "PyPI (Recommended)"

    ```bash
    pip install planopticon
    ```

=== "With cloud sources"

    ```bash
    pip install planopticon[cloud]
    ```

=== "With everything"

    ```bash
    pip install planopticon[all]
    ```

=== "Binary (no Python needed)"

    Download the latest binary for your platform from
    [GitHub Releases](https://github.com/ConflictHQ/PlanOpticon/releases).

## Requirements

- Python 3.10+
- FFmpeg (for audio extraction)
- At least one API key: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY`

## License

MIT License — Copyright (c) 2026 CONFLICT LLC. All rights reserved.
