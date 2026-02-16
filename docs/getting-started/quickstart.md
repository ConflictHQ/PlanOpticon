# Quick Start

## Analyze a single video

```bash
planopticon analyze -i meeting.mp4 -o ./output
```

This runs the full pipeline:

1. Extracts video frames (smart sampling, change detection)
2. Extracts and transcribes audio
3. Detects and analyzes diagrams, charts, whiteboards
4. Builds a knowledge graph of entities and relationships
5. Extracts key points and action items
6. Generates markdown, HTML, and PDF reports
7. Outputs a `manifest.json` with everything

## Processing depth

```bash
# Quick scan — transcription + key points only
planopticon analyze -i video.mp4 -o ./out --depth basic

# Standard — includes diagram extraction (default)
planopticon analyze -i video.mp4 -o ./out --depth standard

# Deep — more frames analyzed, richer extraction
planopticon analyze -i video.mp4 -o ./out --depth comprehensive
```

## Choose a provider

```bash
# Auto-detect best available (default)
planopticon analyze -i video.mp4 -o ./out

# Force a specific provider
planopticon analyze -i video.mp4 -o ./out --provider openai

# Use Ollama for fully offline processing (no API keys needed)
planopticon analyze -i video.mp4 -o ./out --provider ollama

# Override specific models
planopticon analyze -i video.mp4 -o ./out \
    --vision-model gpt-4o \
    --chat-model claude-sonnet-4-5-20250929
```

## Batch processing

```bash
# Process all videos in a folder
planopticon batch -i ./recordings -o ./output

# Custom file patterns
planopticon batch -i ./recordings -o ./output --pattern "*.mp4,*.mov"

# With a title for the batch report
planopticon batch -i ./recordings -o ./output --title "Q4 Sprint Reviews"
```

Batch mode produces per-video outputs plus:

- Merged knowledge graph across all videos
- Batch summary with aggregated action items
- Cross-referenced entities

## Discover available models

```bash
planopticon list-models
```

Shows all models from configured providers with their capabilities (vision, chat, transcription).

## Output structure

After processing, your output directory looks like:

```
output/
├── manifest.json          # Single source of truth
├── transcript/
│   ├── transcript.json    # Full transcript with segments
│   ├── transcript.txt     # Plain text
│   └── transcript.srt     # Subtitles
├── frames/                # Extracted video frames
├── diagrams/              # Detected diagrams + mermaid/SVG/PNG
├── captures/              # Screengrab fallbacks
└── results/
    ├── analysis.md        # Markdown report
    ├── analysis.html      # HTML report
    ├── analysis.pdf       # PDF report
    ├── knowledge_graph.json
    ├── key_points.json
    └── action_items.json
```
