# Processing Pipeline

## Single video pipeline

```mermaid
sequenceDiagram
    participant CLI
    participant Pipeline
    participant FrameExtractor
    participant AudioExtractor
    participant Provider
    participant DiagramAnalyzer
    participant KnowledgeGraph

    CLI->>Pipeline: process_single_video()
    Pipeline->>FrameExtractor: extract_frames()
    Note over FrameExtractor: Change detection + periodic capture (every 30s)
    Pipeline->>Pipeline: filter_people_frames()
    Note over Pipeline: OpenCV face detection removes webcam/people frames
    Pipeline->>AudioExtractor: extract_audio()
    Pipeline->>Provider: transcribe_audio()
    Pipeline->>DiagramAnalyzer: process_frames()

    loop Each frame
        DiagramAnalyzer->>Provider: classify (vision)
        alt High confidence diagram
            DiagramAnalyzer->>Provider: full analysis
        else Medium confidence
            DiagramAnalyzer-->>Pipeline: screengrab fallback
        end
    end

    Pipeline->>KnowledgeGraph: process_transcript()
    Pipeline->>KnowledgeGraph: process_diagrams()
    Pipeline->>Provider: extract key points
    Pipeline->>Provider: extract action items
    Pipeline->>Pipeline: generate reports
    Pipeline->>Pipeline: export formats
    Pipeline-->>CLI: VideoManifest
```

## Batch pipeline

The batch command wraps the single-video pipeline:

1. Scan input directory for matching video files
2. For each video: `process_single_video()` with error handling
3. Merge knowledge graphs across all completed videos
4. Generate batch summary with aggregated stats
5. Write batch manifest

## Error handling

- Individual video failures don't stop the batch
- Failed videos are logged with error details in the manifest
- Diagram analysis failures fall back to screengrabs
- LLM extraction failures return empty results gracefully
