# Provider System

## Overview

PlanOpticon supports multiple AI providers through a unified abstraction layer.

## Supported providers

| Provider | Chat | Vision | Transcription |
|----------|------|--------|--------------|
| OpenAI | GPT-4o, GPT-4 | GPT-4o | Whisper-1 |
| Anthropic | Claude Sonnet/Opus | Claude Sonnet/Opus | — |
| Google Gemini | Gemini Flash/Pro | Gemini Flash/Pro | Gemini Flash |
| Ollama (local) | Any installed model | llava, moondream, etc. | — (use local Whisper) |

## Ollama (offline mode)

[Ollama](https://ollama.com) enables fully offline operation with no API keys required. PlanOpticon connects via Ollama's OpenAI-compatible API.

```bash
# Install and start Ollama
ollama serve

# Pull a chat model
ollama pull llama3.2

# Pull a vision model (for diagram analysis)
ollama pull llava
```

PlanOpticon auto-detects Ollama when it's running. To force Ollama:

```bash
planopticon analyze -i video.mp4 -o ./out --provider ollama
```

Configure a non-default host via `OLLAMA_HOST`:

```bash
export OLLAMA_HOST=http://192.168.1.100:11434
```

## Auto-discovery

On startup, `ProviderManager` checks which API keys are configured, queries each provider's API, and checks for a running Ollama server to discover available models:

```python
from video_processor.providers.manager import ProviderManager

pm = ProviderManager()
# Automatically discovers models from all configured providers + Ollama
```

## Routing preferences

Each task type has a default preference order:

| Task | Preference |
|------|-----------|
| Vision | Gemini Flash → GPT-4o → Claude Sonnet → Ollama |
| Chat | Claude Sonnet → GPT-4o → Gemini Flash → Ollama |
| Transcription | Local Whisper → Whisper-1 → Gemini Flash |

Ollama acts as the last-resort fallback — if no cloud API keys are set but Ollama is running, it is used automatically.

## Manual override

```python
pm = ProviderManager(
    vision_model="gpt-4o",
    chat_model="claude-sonnet-4-5-20250929",
    provider="openai",  # Force a specific provider
)

# Or use Ollama for fully offline processing
pm = ProviderManager(provider="ollama")
```

## BaseProvider interface

All providers implement:

```python
class BaseProvider(ABC):
    def chat(messages, max_tokens, temperature) -> str
    def analyze_image(image_path, prompt, max_tokens) -> str
    def transcribe_audio(audio_path) -> dict
    def list_models() -> List[ModelInfo]
```
