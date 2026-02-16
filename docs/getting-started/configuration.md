# Configuration

## Environment variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GEMINI_API_KEY` | Google Gemini API key |
| `OLLAMA_HOST` | Ollama server URL (default: `http://localhost:11434`) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to Google service account JSON (for Drive) |
| `CACHE_DIR` | Directory for API response caching |

## Provider routing

PlanOpticon auto-discovers available models and routes each task to the best option:

| Task | Default preference |
|------|--------------------|
| Vision (diagrams) | Gemini Flash > GPT-4o > Claude Sonnet > Ollama |
| Chat (analysis) | Claude Sonnet > GPT-4o > Gemini Flash > Ollama |
| Transcription | Local Whisper > Whisper-1 > Gemini Flash |

If no cloud API keys are configured, PlanOpticon automatically falls back to Ollama when a local server is running. This enables fully offline operation when paired with local Whisper for transcription.

Override with `--provider`, `--vision-model`, or `--chat-model` flags.

## Frame sampling

Control how frames are extracted:

```bash
# Sample rate: frames per second (default: 0.5)
planopticon analyze -i video.mp4 -o ./out --sampling-rate 1.0

# Change threshold: visual difference needed to keep a frame (default: 0.15)
planopticon analyze -i video.mp4 -o ./out --change-threshold 0.1

# Periodic capture: capture a frame every N seconds regardless of change (default: 30)
# Useful for slow-evolving content like document scrolling
planopticon analyze -i video.mp4 -o ./out --periodic-capture 15

# Disable periodic capture (rely only on change detection)
planopticon analyze -i video.mp4 -o ./out --periodic-capture 0
```

Lower `change-threshold` = more frames kept. Higher `sampling-rate` = more candidates. Periodic capture catches content that changes too slowly for change detection (e.g., scrolling through a document during a screen share).

People/webcam frames are automatically filtered out using face detection — no configuration needed.

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
