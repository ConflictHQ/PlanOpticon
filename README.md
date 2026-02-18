# PlanOpticon

[![CI](https://github.com/ConflictHQ/PlanOpticon/actions/workflows/ci.yml/badge.svg)](https://github.com/ConflictHQ/PlanOpticon/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/planopticon)](https://pypi.org/project/planopticon/)
[![Python](https://img.shields.io/pypi/pyversions/planopticon)](https://pypi.org/project/planopticon/)
[![License](https://img.shields.io/github/license/ConflictHQ/PlanOpticon)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-planopticon.dev-blue)](https://planopticon.dev)

**AI-powered video analysis and knowledge extraction.**

PlanOpticon processes video recordings into structured knowledge — transcripts, diagrams, action items, key points, and knowledge graphs. It auto-discovers available models across OpenAI, Anthropic, Gemini, and Ollama, and produces rich multi-format output.

## Features

- **Multi-provider AI** — Auto-discovers and routes to the best available model across OpenAI, Anthropic, Google Gemini, and Ollama (fully offline)
- **Smart frame extraction** — Change detection for transitions + periodic capture for slow-evolving content (document scrolling, screen shares)
- **People frame filtering** — OpenCV face detection automatically removes webcam/video conference frames, keeping only shared content
- **Diagram extraction** — Vision model classification detects flowcharts, architecture diagrams, charts, and whiteboards
- **Knowledge graphs** — Extracts entities and relationships, builds and merges knowledge graphs across videos
- **Action item detection** — Finds commitments, tasks, and follow-ups with assignees and deadlines
- **Batch processing** — Process entire folders of videos with merged knowledge graphs and cross-referencing
- **Rich output** — Markdown, HTML, PDF reports. Mermaid diagrams, SVG/PNG renderings, JSON manifests
- **Cloud sources** — Fetch videos from Google Drive and Dropbox shared folders
- **Checkpoint/resume** — Pipeline resumes from where it left off if interrupted
- **Screengrab fallback** — When extraction isn't perfect, captures frames with captions — something is always better than nothing

## Local Run

PlanOpticon runs entirely offline with Ollama — no API keys, no cloud, no cost.

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
# Fully local analysis — no API keys needed, just Ollama running
planopticon analyze -i meeting.mp4 -o ./output \
  --provider ollama \
  --vision-model llava:latest \
  --chat-model qwen3:30b
```

## Quick Start

```bash
# Install
pip install planopticon

# Analyze a single video
planopticon analyze -i meeting.mp4 -o ./output

# Process a folder of videos
planopticon batch -i ./recordings -o ./output --title "Weekly Meetings"

# See available AI models
planopticon list-models
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
    ├── knowledge_graph.json   # Entities and relationships
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

MIT License — Copyright (c) 2026 CONFLICT LLC
