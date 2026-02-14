# Provider System

## Overview

PlanOpticon supports multiple AI providers through a unified abstraction layer.

## Supported providers

| Provider | Chat | Vision | Transcription |
|----------|------|--------|--------------|
| OpenAI | GPT-4o, GPT-4 | GPT-4o | Whisper-1 |
| Anthropic | Claude Sonnet/Opus | Claude Sonnet/Opus | — |
| Google Gemini | Gemini Flash/Pro | Gemini Flash/Pro | Gemini Flash |

## Auto-discovery

On startup, `ProviderManager` checks which API keys are configured and queries each provider's API to discover available models:

```python
from video_processor.providers.manager import ProviderManager

pm = ProviderManager()
# Automatically discovers models from all configured providers
```

## Routing preferences

Each task type has a default preference order:

| Task | Preference |
|------|-----------|
| Vision | Gemini Flash → GPT-4o → Claude Sonnet |
| Chat | Claude Sonnet → GPT-4o → Gemini Flash |
| Transcription | Whisper-1 → Gemini Flash |

## Manual override

```python
pm = ProviderManager(
    vision_model="gpt-4o",
    chat_model="claude-sonnet-4-5-20250929",
    provider="openai",  # Force a specific provider
)
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
