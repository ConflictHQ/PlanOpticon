# PlanOpticon

**AI-powered video analysis and knowledge extraction.**

PlanOpticon processes video recordings into structured knowledge — transcripts, diagrams, action items, key points, and knowledge graphs. It auto-discovers available models across OpenAI, Anthropic, and Gemini, and produces rich multi-format output.

---

## Features

- **Multi-provider AI** — Automatically discovers and routes to the best available model across OpenAI, Anthropic, and Google Gemini
- **Diagram extraction** — Vision model-based classification detects flowcharts, architecture diagrams, charts, and whiteboards
- **Knowledge graphs** — Extracts entities and relationships, builds and merges knowledge graphs across videos
- **Action item detection** — Finds commitments, tasks, and follow-ups with assignees and deadlines
- **Batch processing** — Process entire folders of videos with merged knowledge graphs and cross-referencing
- **Rich output** — Markdown, HTML, PDF, Mermaid diagrams, SVG/PNG renderings, JSON manifests
- **Cloud sources** — Fetch videos from Google Drive and Dropbox shared folders
- **Screengrab fallback** — When extraction isn't perfect, captures frames with captions — something is always better than nothing

## Quick Start

```bash
# Install from PyPI
pip install planopticon

# Analyze a single video
planopticon analyze -i meeting.mp4 -o ./output

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
    [GitHub Releases](https://github.com/conflict-llc/PlanOpticon/releases).

## Requirements

- Python 3.10+
- FFmpeg (for audio extraction)
- At least one API key: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY`

## License

MIT License — Copyright (c) 2025 CONFLICT LLC. All rights reserved.
