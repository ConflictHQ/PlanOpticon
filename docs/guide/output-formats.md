# Output Formats

PlanOpticon produces a wide range of output formats from video analysis, document ingestion, batch processing, knowledge graph export, and agent skills. This page is the comprehensive reference for every format the tool can emit.

---

## Transcripts

Video analysis always produces transcripts in three formats, stored in the `transcript/` subdirectory of the output folder.

| Format | File | Description |
|--------|------|-------------|
| JSON | `transcript/transcript.json` | Full transcript with segments, timestamps, speaker labels, and confidence scores. Each segment includes `start`, `end`, `text`, and optional `speaker` fields. |
| Text | `transcript/transcript.txt` | Plain text transcript with no metadata. Suitable for feeding into other tools or reading directly. |
| SRT | `transcript/transcript.srt` | SubRip subtitle format with sequential numbering and `HH:MM:SS,mmm` timestamps. Can be loaded into video players or subtitle editors. |

### Transcript JSON structure

```json
{
  "segments": [
    {
      "start": 0.0,
      "end": 4.5,
      "text": "Welcome to the sprint review.",
      "speaker": "Alice"
    }
  ],
  "text": "Welcome to the sprint review. ...",
  "language": "en"
}
```

When the `--speakers` flag is provided (e.g., `--speakers "Alice,Bob,Carol"`), speaker diarization hints are passed to the transcription provider and speaker labels appear in the JSON segments.

---

## Reports

Analysis reports are generated from the combined transcript, diagrams, key points, action items, and knowledge graph. They live in the `results/` subdirectory.

| Format | File | Description |
|--------|------|-------------|
| Markdown | `results/analysis.md` | Structured report with embedded Mermaid diagram blocks, tables, and cross-references. Works in any Markdown renderer. |
| HTML | `results/analysis.html` | Self-contained HTML page with inline CSS, embedded SVG diagrams, and a bundled mermaid.js script for rendering any unrendered Mermaid blocks. No external dependencies required to view. |
| PDF | `results/analysis.pdf` | Print-ready PDF. Requires the `planopticon[pdf]` extra (`pip install planopticon[pdf]`). Generated from the HTML report. |

---

## Diagrams

Each visual element detected during frame analysis produces up to five output files in the `diagrams/` subdirectory. The index `N` is zero-based.

| Format | File | Description |
|--------|------|-------------|
| JPEG | `diagrams/diagram_N.jpg` | Original video frame captured at the point of detection. |
| Mermaid | `diagrams/diagram_N.mermaid` | Mermaid source code reconstructed from the diagram by the vision model. Supports flowcharts, sequence diagrams, architecture diagrams, and more. |
| SVG | `diagrams/diagram_N.svg` | Vector rendering of the Mermaid source, produced by the Mermaid CLI or built-in renderer. |
| PNG | `diagrams/diagram_N.png` | Raster rendering of the Mermaid source at high resolution. |
| JSON | `diagrams/diagram_N.json` | Structured analysis data including diagram type, description, extracted text, chart data (if applicable), and confidence score. |

Frames that score as medium confidence are saved as captioned screenshots in the `captures/` subdirectory instead, with a `capture_N.jpg` and `capture_N.json` pair.

---

## Structured Data

Core analysis artifacts are stored as JSON files in the `results/` subdirectory.

| Format | File | Description |
|--------|------|-------------|
| SQLite | `results/knowledge_graph.db` | Primary knowledge graph database. SQLite-based, queryable with `planopticon query`. Contains entities, relationships, source provenance, and metadata. This is the preferred format for querying and merging. |
| JSON | `results/knowledge_graph.json` | JSON export of the knowledge graph. Contains `nodes`, `relationships`, and optional `sources` arrays. Automatically kept in sync with the `.db` file. Used as a fallback when SQLite is not available. |
| JSON | `results/key_points.json` | Array of extracted key points with fields such as `point`, `topic`, `details`, `timestamp`, `source`, and `related_diagrams`. |
| JSON | `results/action_items.json` | Array of action items with fields such as `action`, `assignee`, `deadline`, `priority`, `context`, and `source`. |
| JSON | `manifest.json` | Complete run manifest. The single source of truth for the analysis run. Contains video metadata, processing stats, file paths to all outputs, and inline key points, action items, diagram metadata, and screen captures. |

### Knowledge graph JSON structure

```json
{
  "nodes": [
    {
      "name": "Kubernetes",
      "type": "technology",
      "descriptions": ["Container orchestration platform discussed in architecture review"],
      "occurrences": [
        {"source": "video:recording.mp4", "timestamp": "00:05:23"}
      ]
    }
  ],
  "relationships": [
    {
      "source": "Kubernetes",
      "target": "Docker",
      "type": "depends_on",
      "content_source": "transcript:recording.mp4",
      "timestamp": 323.0
    }
  ],
  "sources": [
    {
      "source_id": "src1",
      "source_type": "video",
      "title": "Architecture Review"
    }
  ]
}
```

---

## Charts

When chart data is extracted from diagrams (bar charts, line charts, pie charts, scatter plots), PlanOpticon reproduces them as standalone image files.

| Format | File | Description |
|--------|------|-------------|
| SVG | `diagrams/chart_N.svg` | Vector chart rendered via matplotlib. Suitable for embedding in documents or scaling to any size. |
| PNG | `diagrams/chart_N.png` | Raster chart rendered via matplotlib at 150 DPI. |

Reproduced charts are also embedded inline in the HTML and PDF reports.

---

## Knowledge Graph Exports

Beyond the default `knowledge_graph.db` and `knowledge_graph.json` produced during analysis, PlanOpticon supports exporting knowledge graphs to several additional formats via the `planopticon export` and `planopticon kg convert` commands.

| Format | Command / File | Description |
|--------|---------------|-------------|
| JSON | `knowledge_graph.json` | Default JSON export. Produced automatically alongside the `.db` file. |
| SQLite | `knowledge_graph.db` | Primary database format. Can be converted to/from JSON with `planopticon kg convert`. |
| GraphML | `output.graphml` | XML-based graph format via `planopticon kg convert kg.db output.graphml`. Compatible with Gephi, yEd, Cytoscape, and other graph visualization tools. |
| CSV | `export/entities.csv`, `export/relationships.csv` | Tabular export via `planopticon export markdown kg.db --type csv`. Produces separate CSV files for entities and relationships. |
| Mermaid | Inline in reports | Mermaid graph diagrams are embedded in Markdown and HTML reports. Also available programmatically via `GraphQueryEngine.to_mermaid()`. |

### Converting between formats

```bash
# SQLite to JSON
planopticon kg convert results/knowledge_graph.db output.json

# JSON to SQLite
planopticon kg convert knowledge_graph.json knowledge_graph.db

# Sync both directions (updates the stale file)
planopticon kg sync results/knowledge_graph.db
planopticon kg sync knowledge_graph.db knowledge_graph.json --direction db-to-json
```

---

## PlanOpticonExchange Format

The PlanOpticonExchange format (`.json`) is a canonical interchange payload designed for sharing knowledge graphs between PlanOpticon instances, teams, or external systems.

```bash
planopticon export exchange knowledge_graph.db
planopticon export exchange kg.db -o exchange.json --name "My Project"
```

The exchange payload includes:

- **Schema version** for forward compatibility
- **Project metadata** (name, description)
- **Full entity and relationship data** with provenance
- **Source tracking** for multi-source graphs
- **Merge support** -- exchange files can be merged together, deduplicating entities by name

### Exchange JSON structure

```json
{
  "version": "1.0",
  "project": {
    "name": "Sprint Reviews Q4",
    "description": "Knowledge extracted from Q4 sprint review recordings"
  },
  "entities": [...],
  "relationships": [...],
  "sources": [...]
}
```

---

## Document Exports

PlanOpticon can generate structured Markdown documents from any knowledge graph, with no API key required. These are pure template-based outputs derived from the graph data.

### Markdown document types

There are seven document types plus a CSV export, all generated via `planopticon export markdown`:

| Type | File | Description |
|------|------|-------------|
| `summary` | `executive_summary.md` | High-level executive summary with entity counts, top relationships, and key themes. |
| `meeting-notes` | `meeting_notes.md` | Structured meeting notes with attendees, topics discussed, decisions made, and action items. |
| `glossary` | `glossary.md` | Alphabetical glossary of all entities with descriptions and types. |
| `relationship-map` | `relationship_map.md` | Textual and Mermaid-based relationship map showing how entities connect. |
| `status-report` | `status_report.md` | Status report format with progress indicators, risks, and next steps. |
| `entity-index` | `entity_index.md` | Comprehensive index of all entities grouped by type, with links to individual briefs. |
| `entity-brief` | `entities/<Name>.md` | One-pager brief for each entity, showing descriptions, relationships, and source references. |
| `csv` | `entities.csv` | Tabular CSV export of entities and relationships. |

```bash
# Generate all document types
planopticon export markdown knowledge_graph.db

# Generate specific types
planopticon export markdown kg.db -o ./docs --type summary --type glossary

# Generate meeting notes and CSV
planopticon export markdown kg.db --type meeting-notes --type csv
```

### Obsidian vault export

Exports the knowledge graph as an Obsidian-compatible vault with YAML frontmatter, `[[wiki-links]]` between entities, and proper folder structure.

```bash
planopticon export obsidian knowledge_graph.db -o ./my-vault
```

The vault includes:

- One note per entity with frontmatter (`type`, `aliases`, `tags`)
- Wiki-links between related entities
- A `_Index.md` file for navigation
- Compatible with Obsidian graph view

### Notion markdown export

Exports as Notion-compatible Markdown with a CSV database file for import into Notion databases.

```bash
planopticon export notion knowledge_graph.db -o ./notion-export
```

### GitHub wiki export

Generates a complete GitHub wiki with a sidebar, home page, and per-entity pages. Can be pushed directly to a GitHub wiki repository.

```bash
# Generate wiki pages
planopticon wiki generate knowledge_graph.db -o ./wiki

# Push to GitHub
planopticon wiki push ./wiki ConflictHQ/PlanOpticon -m "Update wiki from KG"
```

---

## Batch Outputs

Batch processing produces additional files at the batch root directory, alongside per-video output folders.

| Format | File | Description |
|--------|------|-------------|
| JSON | `manifest.json` | Batch-level manifest at the batch root with aggregate stats, per-video status (completed/failed), error details, and paths to all sub-outputs. |
| Markdown | `batch_summary.md` | Aggregated summary report with combined key points, action items, entity counts, and a Mermaid diagram of the merged knowledge graph. |
| SQLite | `knowledge_graph.db` | Merged knowledge graph combining entities and relationships across all successfully processed videos. Uses fuzzy matching and conflict resolution. |
| JSON | `knowledge_graph.json` | JSON export of the merged knowledge graph. |

---

## Self-Contained HTML Viewer

PlanOpticon ships with a self-contained interactive knowledge graph viewer at `knowledge-base/viewer.html` in the repository. This file:

- Uses D3.js (bundled inline, no CDN dependency)
- Renders an interactive force-directed graph visualization
- Supports node filtering by entity type
- Shows entity details and relationships on click
- Can load any `knowledge_graph.json` file
- Works offline with no server required -- just open in a browser
- Covers approximately 80% of graph exploration needs with zero infrastructure

---

## Output Directory Structure

A complete single-video analysis produces the following directory tree:

```
output/
├── manifest.json                      # Run manifest (source of truth)
├── transcript/
│   ├── transcript.json                # Full transcript with segments
│   ├── transcript.txt                 # Plain text
│   └── transcript.srt                 # Subtitles
├── frames/
│   ├── frame_0000.jpg                 # Extracted video frames
│   ├── frame_0001.jpg
│   └── ...
├── diagrams/
│   ├── diagram_0.jpg                  # Original frame
│   ├── diagram_0.mermaid             # Mermaid source
│   ├── diagram_0.svg                 # Vector rendering
│   ├── diagram_0.png                 # Raster rendering
│   ├── diagram_0.json                # Analysis data
│   ├── chart_0.svg                   # Reproduced chart (SVG)
│   ├── chart_0.png                   # Reproduced chart (PNG)
│   └── ...
├── captures/
│   ├── capture_0.jpg                 # Medium-confidence screenshots
│   ├── capture_0.json                # Caption and metadata
│   └── ...
└── results/
    ├── analysis.md                    # Markdown report
    ├── analysis.html                  # HTML report
    ├── analysis.pdf                   # PDF report (if planopticon[pdf] installed)
    ├── knowledge_graph.db             # Knowledge graph (SQLite, primary)
    ├── knowledge_graph.json           # Knowledge graph (JSON export)
    ├── key_points.json                # Extracted key points
    └── action_items.json              # Action items
```

---

## Controlling Output Format

Use the `--output-format` flag with `planopticon analyze` to control how results are presented:

| Value | Behavior |
|-------|----------|
| `default` | Writes all output files to disk and prints a usage summary to stdout. |
| `json` | Writes all output files to disk and also emits the complete `VideoManifest` as structured JSON to stdout. Useful for piping into other tools or CI/CD pipelines. |

```bash
# Standard output (files + console summary)
planopticon analyze -i video.mp4 -o ./output

# JSON manifest to stdout (for scripting)
planopticon analyze -i video.mp4 -o ./output --output-format json
```
