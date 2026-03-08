# Providers API Reference

::: video_processor.providers.base

::: video_processor.providers.manager

::: video_processor.providers.discovery

---

## Overview

The provider system abstracts LLM API calls behind a unified interface. It supports multiple providers (OpenAI, Anthropic, Gemini, Ollama, and OpenAI-compatible services), automatic model discovery, capability-based routing, and usage tracking.

**Key components:**

- **`BaseProvider`** -- abstract interface that all providers implement
- **`ProviderRegistry`** -- global registry mapping provider names to classes
- **`ProviderManager`** -- high-level router that picks the best provider for each task
- **`discover_available_models()`** -- scans all configured providers for available models

---

## BaseProvider (ABC)

```python
from video_processor.providers.base import BaseProvider
```

Abstract base class that all provider implementations must subclass. Defines the four core capabilities: chat, vision, audio transcription, and model listing.

**Class attribute:**

| Attribute | Type | Description |
|---|---|---|
| `provider_name` | `str` | Identifier for this provider (e.g., `"openai"`, `"anthropic"`) |

### chat()

```python
def chat(
    self,
    messages: list[dict],
    max_tokens: int = 4096,
    temperature: float = 0.7,
    model: Optional[str] = None,
) -> str
```

Send a chat completion request.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `messages` | `list[dict]` | *required* | OpenAI-format message list (`role`, `content`) |
| `max_tokens` | `int` | `4096` | Maximum tokens in the response |
| `temperature` | `float` | `0.7` | Sampling temperature |
| `model` | `Optional[str]` | `None` | Override model ID |

**Returns:** `str` -- the assistant's text response.

### analyze_image()

```python
def analyze_image(
    self,
    image_bytes: bytes,
    prompt: str,
    max_tokens: int = 4096,
    model: Optional[str] = None,
) -> str
```

Analyze an image with a text prompt using a vision-capable model.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `image_bytes` | `bytes` | *required* | Raw image data (JPEG, PNG, etc.) |
| `prompt` | `str` | *required* | Analysis instructions |
| `max_tokens` | `int` | `4096` | Maximum tokens in the response |
| `model` | `Optional[str]` | `None` | Override model ID |

**Returns:** `str` -- the assistant's analysis text.

### transcribe_audio()

```python
def transcribe_audio(
    self,
    audio_path: str | Path,
    language: Optional[str] = None,
    model: Optional[str] = None,
) -> dict
```

Transcribe an audio file.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `audio_path` | `str \| Path` | *required* | Path to the audio file |
| `language` | `Optional[str]` | `None` | Language hint (ISO 639-1 code) |
| `model` | `Optional[str]` | `None` | Override model ID |

**Returns:** `dict` -- transcription result with keys `text`, `segments`, `duration`, etc.

### list_models()

```python
def list_models(self) -> list[ModelInfo]
```

Discover available models from this provider's API.

**Returns:** `list[ModelInfo]` -- available models with capability metadata.

---

## ModelInfo

```python
from video_processor.providers.base import ModelInfo
```

Pydantic model describing an available model from a provider.

| Field | Type | Default | Description |
|---|---|---|---|
| `id` | `str` | *required* | Model identifier (e.g., `"gpt-4o"`, `"claude-haiku-4-5-20251001"`) |
| `provider` | `str` | *required* | Provider name (e.g., `"openai"`, `"anthropic"`, `"gemini"`) |
| `display_name` | `str` | `""` | Human-readable display name |
| `capabilities` | `List[str]` | `[]` | Model capabilities: `"chat"`, `"vision"`, `"audio"`, `"embedding"` |

```json
{
  "id": "gpt-4o",
  "provider": "openai",
  "display_name": "GPT-4o",
  "capabilities": ["chat", "vision"]
}
```

---

## ProviderRegistry

```python
from video_processor.providers.base import ProviderRegistry
```

Class-level registry for provider classes. Providers register themselves with metadata on import. This registry is used internally by `ProviderManager` but can also be used directly for introspection.

### register()

```python
@classmethod
def register(
    cls,
    name: str,
    provider_class: type,
    env_var: str = "",
    model_prefixes: Optional[List[str]] = None,
    default_models: Optional[Dict[str, str]] = None,
) -> None
```

Register a provider class with its metadata. Called by each provider module at import time.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | *required* | Provider name (e.g., `"openai"`) |
| `provider_class` | `type` | *required* | The provider class |
| `env_var` | `str` | `""` | Environment variable for API key |
| `model_prefixes` | `Optional[List[str]]` | `None` | Model ID prefixes for auto-detection (e.g., `["gpt-", "o1-"]`) |
| `default_models` | `Optional[Dict[str, str]]` | `None` | Default models per capability (e.g., `{"chat": "gpt-4o", "vision": "gpt-4o"}`) |

### get()

```python
@classmethod
def get(cls, name: str) -> type
```

Return the provider class for a given name. Raises `ValueError` if the provider is not registered.

### get_by_model()

```python
@classmethod
def get_by_model(cls, model_id: str) -> Optional[str]
```

Return the provider name for a model ID based on prefix matching. Returns `None` if no match is found.

### get_default_models()

```python
@classmethod
def get_default_models(cls, name: str) -> Dict[str, str]
```

Return the default models dict for a provider, mapping capability names to model IDs.

### available()

```python
@classmethod
def available(cls) -> List[str]
```

Return names of providers whose required environment variable is set (or providers with no env var requirement, like Ollama).

### all_registered()

```python
@classmethod
def all_registered(cls) -> Dict[str, Dict]
```

Return all registered providers and their metadata dictionaries.

---

## OpenAICompatibleProvider

```python
from video_processor.providers.base import OpenAICompatibleProvider
```

Base class for providers using OpenAI-compatible APIs (Together, Fireworks, Cerebras, xAI, Azure). Implements `chat()`, `analyze_image()`, and `list_models()` using the OpenAI client library. `transcribe_audio()` raises `NotImplementedError` by default.

**Constructor:**

```python
def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `api_key` | `Optional[str]` | `None` | API key (falls back to `self.env_var` environment variable) |
| `base_url` | `Optional[str]` | `None` | API base URL (falls back to `self.base_url` class attribute) |

**Subclass attributes to override:**

| Attribute | Description |
|---|---|
| `provider_name` | Provider identifier string |
| `base_url` | Default API base URL |
| `env_var` | Environment variable name for the API key |

**Usage tracking:** After each `chat()` or `analyze_image()` call, the provider stores token counts in `self._last_usage` as `{"input_tokens": int, "output_tokens": int}`. This is consumed by `ProviderManager._track()`.

---

## ProviderManager

```python
from video_processor.providers.manager import ProviderManager
```

High-level router that selects the best available provider and model for each API call. Supports explicit model selection, forced provider, or automatic selection based on discovered capabilities.

### Constructor

```python
def __init__(
    self,
    vision_model: Optional[str] = None,
    chat_model: Optional[str] = None,
    transcription_model: Optional[str] = None,
    provider: Optional[str] = None,
    auto: bool = True,
)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `vision_model` | `Optional[str]` | `None` | Override model for vision tasks (e.g., `"gpt-4o"`) |
| `chat_model` | `Optional[str]` | `None` | Override model for chat/LLM tasks |
| `transcription_model` | `Optional[str]` | `None` | Override model for transcription |
| `provider` | `Optional[str]` | `None` | Force all tasks to a single provider |
| `auto` | `bool` | `True` | If `True` and no model specified, pick the best available |

**Attributes:**

| Attribute | Type | Description |
|---|---|---|
| `usage` | `UsageTracker` | Tracks token counts and API costs across all calls |

### Auto-selection preferences

When `auto=True` and no explicit model is set, providers are tried in this order:

**Vision:** Gemini (`gemini-2.5-flash`) > OpenAI (`gpt-4o-mini`) > Anthropic (`claude-haiku-4-5-20251001`)

**Chat:** Anthropic (`claude-haiku-4-5-20251001`) > OpenAI (`gpt-4o-mini`) > Gemini (`gemini-2.5-flash`)

**Transcription:** OpenAI (`whisper-1`) > Gemini (`gemini-2.5-flash`)

If no API-key-based provider is available, Ollama is tried as a fallback.

### chat()

```python
def chat(
    self,
    messages: list[dict],
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str
```

Send a chat completion to the best available provider. Automatically resolves which provider and model to use.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `messages` | `list[dict]` | *required* | OpenAI-format messages |
| `max_tokens` | `int` | `4096` | Maximum response tokens |
| `temperature` | `float` | `0.7` | Sampling temperature |

**Returns:** `str` -- assistant response text.

**Raises:** `RuntimeError` if no provider is available for the `chat` capability.

### analyze_image()

```python
def analyze_image(
    self,
    image_bytes: bytes,
    prompt: str,
    max_tokens: int = 4096,
) -> str
```

Analyze an image using the best available vision provider.

**Returns:** `str` -- analysis text.

**Raises:** `RuntimeError` if no provider is available for the `vision` capability.

### transcribe_audio()

```python
def transcribe_audio(
    self,
    audio_path: str | Path,
    language: Optional[str] = None,
    speaker_hints: Optional[list[str]] = None,
) -> dict
```

Transcribe audio. Prefers local Whisper (no file size limits, no API costs) when available, falling back to API-based transcription.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `audio_path` | `str \| Path` | *required* | Path to the audio file |
| `language` | `Optional[str]` | `None` | Language hint |
| `speaker_hints` | `Optional[list[str]]` | `None` | Speaker names for better recognition |

**Returns:** `dict` -- transcription result with `text`, `segments`, `duration`.

**Local Whisper:** If `transcription_model` is unset or starts with `"whisper-local"`, the manager tries local Whisper first. Use `"whisper-local:large"` to specify a model size.

### get_models_used()

```python
def get_models_used(self) -> dict[str, str]
```

Return a dict mapping capability to `"provider/model"` string for tracking purposes.

```python
pm = ProviderManager()
print(pm.get_models_used())
# {"vision": "gemini/gemini-2.5-flash", "chat": "anthropic/claude-haiku-4-5-20251001", ...}
```

### Usage examples

```python
from video_processor.providers.manager import ProviderManager

# Auto-select best providers
pm = ProviderManager()

# Force everything through one provider
pm = ProviderManager(provider="openai")

# Explicit model selection
pm = ProviderManager(
    vision_model="gpt-4o",
    chat_model="claude-haiku-4-5-20251001",
    transcription_model="whisper-local:large",
)

# Chat completion
response = pm.chat([
    {"role": "user", "content": "Summarize this meeting transcript..."}
])

# Image analysis
with open("diagram.png", "rb") as f:
    analysis = pm.analyze_image(f.read(), "Describe this architecture diagram")

# Transcription with speaker hints
result = pm.transcribe_audio(
    "meeting.mp3",
    language="en",
    speaker_hints=["Alice", "Bob", "Charlie"],
)

# Check usage
print(pm.usage.summary())
```

---

## discover_available_models()

```python
from video_processor.providers.discovery import discover_available_models
```

```python
def discover_available_models(
    api_keys: Optional[dict[str, str]] = None,
    force_refresh: bool = False,
) -> list[ModelInfo]
```

Discover available models from all configured providers. For each provider with a valid API key, calls `list_models()` and returns a unified, sorted list.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `api_keys` | `Optional[dict[str, str]]` | `None` | Override API keys (defaults to environment variables) |
| `force_refresh` | `bool` | `False` | Force re-discovery, ignoring the session cache |

**Returns:** `list[ModelInfo]` -- all discovered models, sorted by provider then model ID.

**Caching:** Results are cached for the session. Use `force_refresh=True` or `clear_discovery_cache()` to refresh.

```python
from video_processor.providers.discovery import (
    discover_available_models,
    clear_discovery_cache,
)

# Discover models using environment variables
models = discover_available_models()
for m in models:
    print(f"{m.provider}/{m.id} - {m.capabilities}")

# Force refresh
models = discover_available_models(force_refresh=True)

# Override API keys
models = discover_available_models(api_keys={
    "openai": "sk-...",
    "anthropic": "sk-ant-...",
})

# Clear cache
clear_discovery_cache()
```

### clear_discovery_cache()

```python
def clear_discovery_cache() -> None
```

Clear the cached model list, forcing the next `discover_available_models()` call to re-query providers.

---

## Built-in Providers

The following providers are registered automatically when the provider system initializes:

| Provider | Environment Variable | Capabilities | Default Chat Model |
|---|---|---|---|
| `openai` | `OPENAI_API_KEY` | chat, vision, audio | `gpt-4o-mini` |
| `anthropic` | `ANTHROPIC_API_KEY` | chat, vision | `claude-haiku-4-5-20251001` |
| `gemini` | `GEMINI_API_KEY` | chat, vision, audio | `gemini-2.5-flash` |
| `ollama` | *(none -- checks server)* | chat, vision | *(depends on installed models)* |
| `together` | `TOGETHER_API_KEY` | chat | *(varies)* |
| `fireworks` | `FIREWORKS_API_KEY` | chat | *(varies)* |
| `cerebras` | `CEREBRAS_API_KEY` | chat | *(varies)* |
| `xai` | `XAI_API_KEY` | chat | *(varies)* |
| `azure` | `AZURE_OPENAI_API_KEY` | chat, vision | *(varies)* |
