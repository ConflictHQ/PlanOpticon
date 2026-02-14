# Output Formats

PlanOpticon produces multiple output formats from each analysis run.

## Transcripts

| Format | File | Description |
|--------|------|-------------|
| JSON | `transcript/transcript.json` | Full transcript with segments, timestamps, speakers |
| Text | `transcript/transcript.txt` | Plain text transcript |
| SRT | `transcript/transcript.srt` | Subtitle format with timestamps |

## Reports

| Format | File | Description |
|--------|------|-------------|
| Markdown | `results/analysis.md` | Structured report with diagrams |
| HTML | `results/analysis.html` | Self-contained HTML with mermaid.js |
| PDF | `results/analysis.pdf` | Print-ready PDF (requires `planopticon[pdf]`) |

## Diagrams

Each detected diagram produces:

| Format | File | Description |
|--------|------|-------------|
| JPEG | `diagrams/diagram_N.jpg` | Original frame |
| Mermaid | `diagrams/diagram_N.mermaid` | Mermaid source code |
| SVG | `diagrams/diagram_N.svg` | Vector rendering |
| PNG | `diagrams/diagram_N.png` | Raster rendering |
| JSON | `diagrams/diagram_N.json` | Structured analysis data |

## Structured data

| Format | File | Description |
|--------|------|-------------|
| JSON | `results/knowledge_graph.json` | Entities and relationships |
| JSON | `results/key_points.json` | Extracted key points |
| JSON | `results/action_items.json` | Action items with assignees |
| JSON | `manifest.json` | Complete run manifest |

## Charts

When chart data is extracted from diagrams (bar, line, pie, scatter), PlanOpticon reproduces them:

- SVG + PNG via matplotlib
- Embedded in HTML/PDF reports
