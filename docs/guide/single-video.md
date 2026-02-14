# Single Video Analysis

## Basic usage

```bash
planopticon analyze -i recording.mp4 -o ./output
```

## What happens

The pipeline runs these steps in order:

1. **Frame extraction** — Samples frames from the video using change detection to avoid duplicates
2. **Audio extraction** — Extracts audio track to WAV
3. **Transcription** — Sends audio to speech-to-text (Whisper or Gemini)
4. **Diagram detection** — Vision model classifies each frame as diagram/chart/whiteboard/screenshot/none
5. **Diagram analysis** — High-confidence diagrams get full extraction (description, text, mermaid, chart data)
6. **Screengrab fallback** — Medium-confidence frames are saved as captioned screenshots
7. **Knowledge graph** — Extracts entities and relationships from transcript + diagrams
8. **Key points** — LLM extracts main points and topics
9. **Action items** — LLM finds tasks, commitments, and follow-ups
10. **Reports** — Generates markdown, HTML, and PDF
11. **Export** — Renders mermaid diagrams to SVG/PNG, reproduces charts

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
    "diagrams_detected": 3,
    "screen_captures": 5
  },
  "key_points": [...],
  "action_items": [...],
  "diagrams": [...],
  "screen_captures": [...]
}
```
