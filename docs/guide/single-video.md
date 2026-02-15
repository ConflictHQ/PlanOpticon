# Single Video Analysis

## Basic usage

```bash
planopticon analyze -i recording.mp4 -o ./output
```

## What happens

The pipeline runs these steps in order:

1. **Frame extraction** — Samples frames using change detection for transitions plus periodic capture (every 30s) for slow-evolving content like document scrolling
2. **People frame filtering** — OpenCV face detection automatically removes webcam/video conference frames, keeping only shared content (slides, documents, screen shares)
3. **Audio extraction** — Extracts audio track to WAV
4. **Transcription** — Sends audio to speech-to-text (Whisper or Gemini)
5. **Diagram detection** — Vision model classifies each frame as diagram/chart/whiteboard/screenshot/none
6. **Diagram analysis** — High-confidence diagrams get full extraction (description, text, mermaid, chart data)
7. **Screengrab fallback** — Medium-confidence frames are saved as captioned screenshots
8. **Knowledge graph** — Extracts entities and relationships from transcript + diagrams
9. **Key points** — LLM extracts main points and topics
10. **Action items** — LLM finds tasks, commitments, and follow-ups
11. **Reports** — Generates markdown, HTML, and PDF
12. **Export** — Renders mermaid diagrams to SVG/PNG, reproduces charts

## Processing depth

### `basic`
- Transcription only
- Key points and action items
- No diagram extraction

### `standard` (default)
- Everything in basic
- Diagram extraction (up to 10 frames)
- Knowledge graph
- Full report generation

### `comprehensive`
- Everything in standard
- More frames analyzed (up to 20)
- Deeper analysis

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
    "screen_captures": 5
  },
  "key_points": [...],
  "action_items": [...],
  "diagrams": [...],
  "screen_captures": [...]
}
```
