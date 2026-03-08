# Single Video Analysis

## Basic usage

```bash
planopticon analyze -i recording.mp4 -o ./output
```

## What happens

The pipeline runs these steps in order:

1. **Frame extraction** -- Samples frames using change detection for transitions plus periodic capture (every 30s) for slow-evolving content like document scrolling
2. **People frame filtering** -- OpenCV face detection automatically removes webcam/video conference frames, keeping only shared content (slides, documents, screen shares)
3. **Audio extraction** -- Extracts audio track to WAV
4. **Transcription** -- Sends audio to speech-to-text (Whisper or Gemini). If `--speakers` is provided, speaker diarization hints are passed to the provider.
5. **Diagram detection** -- Vision model classifies each frame as diagram/chart/whiteboard/screenshot/none
6. **Diagram analysis** -- High-confidence diagrams get full extraction (description, text, mermaid, chart data)
7. **Screengrab fallback** -- Medium-confidence frames are saved as captioned screenshots
8. **Knowledge graph** -- Extracts entities and relationships from transcript + diagrams, stored in both `knowledge_graph.db` (SQLite, primary) and `knowledge_graph.json` (export)
9. **Key points** -- LLM extracts main points and topics
10. **Action items** -- LLM finds tasks, commitments, and follow-ups
11. **Reports** -- Generates markdown, HTML, and PDF
12. **Export** -- Renders mermaid diagrams to SVG/PNG, reproduces charts

After analysis, you can optionally run planning taxonomy classification on the knowledge graph to categorize entities for use with the planning agent:

```bash
planopticon kg classify results/knowledge_graph.db
```

## Processing depth

### `basic`
- Transcription only
- Key points and action items
- No diagram extraction

### `standard` (default)
- Everything in basic
- Diagram extraction (up to 10 frames, evenly sampled)
- Knowledge graph
- Full report generation

### `comprehensive`
- Everything in standard
- More frames analyzed (up to 20)
- Deeper analysis

## Command-line options

### Provider and model selection

```bash
# Use a specific provider
planopticon analyze -i video.mp4 -o ./output --provider anthropic

# Override vision and chat models separately
planopticon analyze -i video.mp4 -o ./output --vision-model gpt-4o --chat-model claude-sonnet-4-20250514
```

### Speaker diarization hints

Use `--speakers` to provide speaker names as comma-separated hints. These are passed to the transcription provider to improve speaker identification in the transcript segments.

```bash
planopticon analyze -i video.mp4 -o ./output --speakers "Alice,Bob,Carol"
```

### Custom prompt templates

Use `--templates-dir` to point to a directory of custom `.txt` prompt template files. These override the built-in prompts used for diagram analysis, key point extraction, action item extraction, and other LLM-driven steps.

```bash
planopticon analyze -i video.mp4 -o ./output --templates-dir ./my-prompts
```

Template files should be named to match the built-in template names (e.g., `key_points.txt`, `action_items.txt`). See the `video_processor/utils/prompt_templates.py` module for the full list of template names.

### Output format

Use `--output-format json` to emit the complete `VideoManifest` as structured JSON to stdout, in addition to writing all output files to disk. This is useful for scripting, CI/CD integration, or piping results into other tools.

```bash
# Standard output (files + console summary)
planopticon analyze -i video.mp4 -o ./output

# JSON manifest to stdout
planopticon analyze -i video.mp4 -o ./output --output-format json
```

### Frame extraction tuning

```bash
# Adjust sampling rate (frames per second to consider)
planopticon analyze -i video.mp4 -o ./output --sampling-rate 1.0

# Adjust change detection threshold (lower = more sensitive)
planopticon analyze -i video.mp4 -o ./output --change-threshold 0.10

# Adjust periodic capture interval
planopticon analyze -i video.mp4 -o ./output --periodic-capture 60

# Enable GPU acceleration for frame extraction
planopticon analyze -i video.mp4 -o ./output --use-gpu
```

## Output structure

Every run produces a standardized directory structure:

```
output/
├── manifest.json                      # Run manifest (source of truth)
├── transcript/
│   ├── transcript.json                # Full transcript with segments + speakers
│   ├── transcript.txt                 # Plain text
│   └── transcript.srt                 # Subtitles
├── frames/
│   ├── frame_0000.jpg
│   └── ...
├── diagrams/
│   ├── diagram_0.jpg                  # Original frame
│   ├── diagram_0.mermaid             # Mermaid source
│   ├── diagram_0.svg                 # Vector rendering
│   ├── diagram_0.png                 # Raster rendering
│   ├── diagram_0.json                # Analysis data
│   └── ...
├── captures/
│   ├── capture_0.jpg                 # Medium-confidence screenshots
│   ├── capture_0.json
│   └── ...
└── results/
    ├── analysis.md                    # Markdown report
    ├── analysis.html                  # HTML report
    ├── analysis.pdf                   # PDF (if planopticon[pdf] installed)
    ├── knowledge_graph.db             # Knowledge graph (SQLite, primary)
    ├── knowledge_graph.json           # Knowledge graph (JSON export)
    ├── key_points.json                # Extracted key points
    └── action_items.json              # Action items
```

## Output manifest

Every run produces a `manifest.json` that is the single source of truth:

```json
{
  "version": "1.0",
  "video": {
    "title": "Analysis of recording",
    "source_path": "/path/to/recording.mp4",
    "duration_seconds": 3600.0
  },
  "stats": {
    "duration_seconds": 45.2,
    "frames_extracted": 42,
    "people_frames_filtered": 11,
    "diagrams_detected": 3,
    "screen_captures": 5,
    "models_used": {
      "vision": "gpt-4o",
      "chat": "gpt-4o"
    }
  },
  "transcript_json": "transcript/transcript.json",
  "transcript_txt": "transcript/transcript.txt",
  "transcript_srt": "transcript/transcript.srt",
  "analysis_md": "results/analysis.md",
  "knowledge_graph_json": "results/knowledge_graph.json",
  "knowledge_graph_db": "results/knowledge_graph.db",
  "key_points_json": "results/key_points.json",
  "action_items_json": "results/action_items.json",
  "key_points": [...],
  "action_items": [...],
  "diagrams": [...],
  "screen_captures": [...]
}
```

## Checkpoint and resume

The pipeline supports checkpoint/resume. If a step's output files already exist on disk, that step is skipped on re-run. This means you can safely re-run an interrupted analysis and it will pick up where it left off:

```bash
# First run (interrupted at step 6)
planopticon analyze -i video.mp4 -o ./output

# Second run (resumes from step 6)
planopticon analyze -i video.mp4 -o ./output
```

## Using results after analysis

### Query the knowledge graph

After analysis completes, you can query the knowledge graph directly:

```bash
# Show graph stats
planopticon query --db results/knowledge_graph.db

# List entities by type
planopticon query --db results/knowledge_graph.db "entities --type technology"

# Find neighbors of an entity
planopticon query --db results/knowledge_graph.db "neighbors Kubernetes"

# Ask natural language questions (requires API key)
planopticon query --db results/knowledge_graph.db "What technologies were discussed?"
```

### Classify entities for planning

Run taxonomy classification to categorize entities into planning types (goal, milestone, risk, dependency, etc.):

```bash
planopticon kg classify results/knowledge_graph.db
planopticon kg classify results/knowledge_graph.db --format json
```

### Export to other formats

```bash
# Generate markdown documents
planopticon export markdown results/knowledge_graph.db -o ./docs

# Export as Obsidian vault
planopticon export obsidian results/knowledge_graph.db -o ./vault

# Export as PlanOpticonExchange
planopticon export exchange results/knowledge_graph.db -o exchange.json

# Generate GitHub wiki
planopticon wiki generate results/knowledge_graph.db -o ./wiki
```

### Use with the planning agent

The planning agent can consume the knowledge graph to generate project plans, PRDs, roadmaps, and other planning artifacts:

```bash
planopticon agent --db results/knowledge_graph.db
```
