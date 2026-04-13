# Batch Processing

## Basic usage

```bash
planopticon batch -i ./recordings -o ./output --title "Sprint Reviews"
```

## How it works

Batch mode:

1. Scans the input directory for video files matching the pattern
2. Processes each video through the full single-video pipeline
3. Merges knowledge graphs across all videos with fuzzy matching and conflict resolution
4. Generates a batch summary with aggregated stats and action items
5. Writes a batch manifest (`manifest.json` at the batch root) linking to per-video results

## File patterns

```bash
# Default: common video formats
planopticon batch -i ./recordings -o ./output

# Custom patterns
planopticon batch -i ./recordings -o ./output --pattern "*.mp4,*.mov"
```

## Output structure

```
output/
├── manifest.json             # Batch-level manifest
├── batch_summary.md          # Aggregated summary
├── knowledge_graph.db        # Merged KG across all videos (SQLite, primary)
├── knowledge_graph.json      # Merged KG across all videos (JSON export)
└── videos/
    ├── meeting-01/
    │   ├── manifest.json
    │   ├── transcript/
    │   ├── diagrams/
    │   ├── captures/
    │   └── results/
    │       ├── analysis.md
    │       ├── analysis.html
    │       ├── knowledge_graph.db
    │       ├── knowledge_graph.json
    │       ├── key_points.json
    │       └── action_items.json
    └── meeting-02/
        ├── manifest.json
        └── ...
```

## Knowledge graph merging

When the same entity appears across multiple videos, PlanOpticon merges them using a multi-strategy approach:

### Entity deduplication

- **Case-insensitive exact matching** -- `"kubernetes"` and `"Kubernetes"` are recognized as the same entity
- **Fuzzy name matching** -- Uses `SequenceMatcher` with a threshold of 0.85 to unify near-duplicate entities (e.g., `"K8s"` and `"k8s cluster"` may be matched depending on context)
- **Descriptions are unioned** -- All unique descriptions from each video are combined
- **Occurrences are concatenated with source tracking** -- Each occurrence retains its source video reference

### Relationship deduplication

- Relationships are deduplicated by (source, target, type) tuple
- Descriptions from duplicate relationships are merged

### Type conflict resolution

When the same entity appears with different types across videos, PlanOpticon uses a specificity ranking to resolve the conflict. More specific types are preferred over general ones:

- `technology` > `concept`
- `person` > `concept`
- `organization` > `concept`
- And so on through the full type hierarchy

This ensures that an entity initially classified as a generic `concept` in one video gets upgraded to `technology` if it is identified more specifically in another.

The merged knowledge graph is saved at the batch root in both SQLite (`knowledge_graph.db`) and JSON (`knowledge_graph.json`) formats, and is included in the batch summary as a Mermaid diagram.

## Error handling

If a video fails to process, the batch continues. Failed videos are recorded in the batch manifest with error details:

```json
{
  "video_name": "corrupted-file",
  "status": "failed",
  "error": "Audio extraction failed: no audio track found"
}
```

The batch manifest tracks completion status:

```json
{
  "title": "Sprint Reviews",
  "total_videos": 5,
  "completed_videos": 4,
  "failed_videos": 1,
  "total_diagrams": 12,
  "total_action_items": 23,
  "total_key_points": 45,
  "videos": [...],
  "batch_summary_md": "batch_summary.md",
  "merged_knowledge_graph_json": "knowledge_graph.json",
  "merged_knowledge_graph_db": "knowledge_graph.db"
}
```

## Using batch results

### Query the merged knowledge graph

After batch processing completes, the merged knowledge graph at the batch root contains entities and relationships from all successfully processed videos. You can query it just like a single-video knowledge graph:

```bash
# Show stats for the merged graph
planopticon query --db output/knowledge_graph.db

# List all people mentioned across all videos
planopticon query --db output/knowledge_graph.db "entities --type person"

# See what connects to an entity across all videos
planopticon query --db output/knowledge_graph.db "neighbors Alice"

# Ask natural language questions about the combined content
planopticon query --db output/knowledge_graph.db "What technologies were discussed across all meetings?"

# Interactive REPL for exploration
planopticon query --db output/knowledge_graph.db -I
```

### Export merged results

All export commands work with the merged knowledge graph:

```bash
# Generate documents from merged KG
planopticon export markdown output/knowledge_graph.db -o ./docs

# Export as Obsidian vault
planopticon export obsidian output/knowledge_graph.db -o ./vault

# Generate a project-wide exchange file
planopticon export exchange output/knowledge_graph.db --name "Sprint Reviews Q4"

# Generate a GitHub wiki
planopticon wiki generate output/knowledge_graph.db -o ./wiki
```

### Classify for planning

Run taxonomy classification on the merged graph to categorize entities across all videos:

```bash
planopticon kg classify output/knowledge_graph.db
```

### Use with the planning agent

The planning agent can consume the merged knowledge graph for cross-video analysis and planning:

```bash
planopticon agent --db output/knowledge_graph.db
```

### Incremental batch processing

If you add new videos to the recordings directory, you can re-run the batch command. Videos that have already been processed (with output directories present) will be detected via checkpoint/resume within each video's pipeline, making incremental processing efficient.

```bash
# Add new recordings to the folder, then re-run
planopticon batch -i ./recordings -o ./output --title "Sprint Reviews"
```
