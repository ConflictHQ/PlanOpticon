# Configuration

## Environment variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to Google service account JSON (for Drive) |
| `CACHE_DIR` | Directory for API response caching |

## Provider routing

PlanOpticon auto-discovers available models and routes each task to the best option:

| Task | Default preference |
|------|--------------------|
| Vision (diagrams) | Gemini Flash > GPT-4o > Claude Sonnet |
| Chat (analysis) | Claude Sonnet > GPT-4o > Gemini Flash |
| Transcription | Whisper-1 > Gemini Flash |

Override with `--provider`, `--vision-model`, or `--chat-model` flags.

## Frame sampling

Control how frames are extracted:

```bash
# Sample rate: frames per second (default: 0.5)
planopticon analyze -i video.mp4 -o ./out --sampling-rate 1.0

# Change threshold: visual difference needed to keep a frame (default: 0.15)
planopticon analyze -i video.mp4 -o ./out --change-threshold 0.1
```

Lower `change-threshold` = more frames kept. Higher `sampling-rate` = more candidates.

## Focus areas

Limit processing to specific extraction types:

```bash
planopticon analyze -i video.mp4 -o ./out --focus "diagrams,action-items"
```

## GPU acceleration

```bash
planopticon analyze -i video.mp4 -o ./out --use-gpu
```

Requires `planopticon[gpu]` extras installed.
