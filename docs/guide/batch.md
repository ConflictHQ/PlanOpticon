# Batch Processing

## Basic usage

```bash
planopticon batch -i ./recordings -o ./output --title "Sprint Reviews"
```

## How it works

Batch mode:

1. Scans the input directory for video files matching the pattern
2. Processes each video through the full single-video pipeline
3. Merges knowledge graphs across all videos (case-insensitive entity dedup)
4. Generates a batch summary with aggregated stats and action items
5. Writes a batch manifest linking to per-video results

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
├── batch_manifest.json       # Batch-level manifest
├── batch_summary.md          # Aggregated summary
├── knowledge_graph.json      # Merged KG across all videos
└── videos/
    ├── meeting-01/
    │   ├── manifest.json
    │   ├── transcript/
    │   ├── diagrams/
    │   └── results/
    └── meeting-02/
        ├── manifest.json
        └── ...
```

## Knowledge graph merging

When the same entity appears across multiple videos, PlanOpticon merges them:

- Case-insensitive name matching
- Descriptions are unioned
- Occurrences are concatenated with source tracking
- Relationships are deduplicated

The merged knowledge graph is saved at the batch root and included in the batch summary as a mermaid diagram.

## Error handling

If a video fails to process, the batch continues. Failed videos are recorded in the batch manifest with error details:

```json
{
  "video_name": "corrupted-file",
  "status": "failed",
  "error": "Audio extraction failed: no audio track found"
}
```
