# Provider System

## Overview

PlanOpticon supports multiple AI providers through a unified abstraction layer. Default models favor cost-effective options (Haiku, GPT-4o-mini, Gemini Flash) for routine tasks, with more capable models available when needed.

## Supported providers

| Provider | Chat | Vision | Transcription | Env Variable |
|----------|------|--------|--------------|--------------|
| OpenAI | GPT-4o-mini, GPT-4o | GPT-4o-mini, GPT-4o | Whisper-1 | `OPENAI_API_KEY` |
| Anthropic | Claude Haiku, Sonnet, Opus | Claude Haiku, Sonnet, Opus | — | `ANTHROPIC_API_KEY` |
| Google Gemini | Gemini Flash, Pro | Gemini Flash, Pro | Gemini Flash | `GEMINI_API_KEY` |
| Azure OpenAI | GPT-4o-mini, GPT-4o | GPT-4o-mini, GPT-4o | Whisper-1 | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` |
| Together AI | Llama, Mixtral, etc. | Llava | — | `TOGETHER_API_KEY` |
| Fireworks AI | Llama, Mixtral, etc. | Llava | — | `FIREWORKS_API_KEY` |
| Cerebras | Llama (fast inference) | — | — | `CEREBRAS_API_KEY` |
| xAI | Grok | Grok | — | `XAI_API_KEY` |
| Replicate | Llama 3, etc. | Llava | Whisper | `REPLICATE_API_TOKEN` |
| Ollama (local) | Any installed model | llava, moondream, etc. | — (use local Whisper) | `OLLAMA_HOST` |

## Default models

PlanOpticon defaults to cheap, fast models for cost efficiency:

| Task | Default model |
|------|--------------|
| Vision (diagrams) | Gemini Flash |
| Chat (analysis) | Claude Haiku |
| Transcription | Local Whisper (fallback: Whisper-1) |

Use `--vision-model` and `--chat-model` to override with more capable models when needed (e.g., `--chat-model claude-sonnet-4-20250514` for complex analysis).

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

Each task type has a default preference order (cheapest first):

| Task | Preference |
|------|-----------|
| Vision | Gemini Flash → GPT-4o-mini → Claude Haiku → Ollama |
| Chat | Claude Haiku → GPT-4o-mini → Gemini Flash → Ollama |
| Transcription | Local Whisper → Whisper-1 → Gemini Flash |

Ollama acts as the last-resort fallback -- if no cloud API keys are set but Ollama is running, it is used automatically.

## Manual override

```python
pm = ProviderManager(
    vision_model="gpt-4o",
    chat_model="claude-sonnet-4-20250514",
    provider="openai",  # Force a specific provider
)

# Use a cheap model for bulk processing
pm = ProviderManager(
    chat_model="claude-haiku-3-5-20241022",
    vision_model="gemini-2.0-flash",
)

# Or use Ollama for fully offline processing
pm = ProviderManager(provider="ollama")

# Use Azure OpenAI
pm = ProviderManager(provider="azure")

# Use Together AI for open-source models
pm = ProviderManager(provider="together", chat_model="meta-llama/Llama-3.3-70B-Instruct-Turbo")
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
