"""ProviderManager - unified interface for routing API calls to the best available provider."""

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from video_processor.providers.base import BaseProvider, ModelInfo
from video_processor.providers.discovery import discover_available_models
from video_processor.utils.usage_tracker import UsageTracker

load_dotenv()
logger = logging.getLogger(__name__)

# Default model preference rankings (tried in order)
_VISION_PREFERENCES = [
    ("gemini", "gemini-2.5-flash"),
    ("openai", "gpt-4o"),
    ("anthropic", "claude-sonnet-4-5-20250929"),
]

_CHAT_PREFERENCES = [
    ("anthropic", "claude-sonnet-4-5-20250929"),
    ("openai", "gpt-4o"),
    ("gemini", "gemini-2.5-flash"),
]

_TRANSCRIPTION_PREFERENCES = [
    ("openai", "whisper-1"),
    ("gemini", "gemini-2.5-flash"),
]


class ProviderManager:
    """
    Routes API calls to the best available provider/model.

    Supports explicit model selection or auto-routing based on
    discovered available models.
    """

    def __init__(
        self,
        vision_model: Optional[str] = None,
        chat_model: Optional[str] = None,
        transcription_model: Optional[str] = None,
        provider: Optional[str] = None,
        auto: bool = True,
    ):
        """
        Initialize the ProviderManager.

        Parameters
        ----------
        vision_model : override model for vision tasks (e.g. 'gpt-4o')
        chat_model : override model for chat/LLM tasks
        transcription_model : override model for transcription
        provider : force all tasks to a single provider ('openai', 'anthropic', 'gemini')
        auto : if True and no model specified, pick the best available
        """
        self.auto = auto
        self._providers: dict[str, BaseProvider] = {}
        self._available_models: Optional[list[ModelInfo]] = None
        self.usage = UsageTracker()

        # If a single provider is forced, apply it
        if provider:
            self.vision_model = vision_model or self._default_for_provider(provider, "vision")
            self.chat_model = chat_model or self._default_for_provider(provider, "chat")
            self.transcription_model = transcription_model or self._default_for_provider(provider, "audio")
        else:
            self.vision_model = vision_model
            self.chat_model = chat_model
            self.transcription_model = transcription_model

        self._forced_provider = provider

    @staticmethod
    def _default_for_provider(provider: str, capability: str) -> str:
        """Return the default model for a provider/capability combo."""
        defaults = {
            "openai": {"chat": "gpt-4o", "vision": "gpt-4o", "audio": "whisper-1"},
            "anthropic": {"chat": "claude-sonnet-4-5-20250929", "vision": "claude-sonnet-4-5-20250929", "audio": ""},
            "gemini": {"chat": "gemini-2.5-flash", "vision": "gemini-2.5-flash", "audio": "gemini-2.5-flash"},
        }
        return defaults.get(provider, {}).get(capability, "")

    def _get_provider(self, provider_name: str) -> BaseProvider:
        """Lazily initialize and cache a provider instance."""
        if provider_name not in self._providers:
            if provider_name == "openai":
                from video_processor.providers.openai_provider import OpenAIProvider
                self._providers[provider_name] = OpenAIProvider()
            elif provider_name == "anthropic":
                from video_processor.providers.anthropic_provider import AnthropicProvider
                self._providers[provider_name] = AnthropicProvider()
            elif provider_name == "gemini":
                from video_processor.providers.gemini_provider import GeminiProvider
                self._providers[provider_name] = GeminiProvider()
            else:
                raise ValueError(f"Unknown provider: {provider_name}")
        return self._providers[provider_name]

    def _provider_for_model(self, model_id: str) -> str:
        """Infer the provider from a model id."""
        if model_id.startswith("gpt-") or model_id.startswith("o1") or model_id.startswith("o3") or model_id.startswith("o4") or model_id.startswith("whisper"):
            return "openai"
        if model_id.startswith("claude-"):
            return "anthropic"
        if model_id.startswith("gemini-"):
            return "gemini"
        # Try discovery
        models = self._get_available_models()
        for m in models:
            if m.id == model_id:
                return m.provider
        raise ValueError(f"Cannot determine provider for model: {model_id}")

    def _get_available_models(self) -> list[ModelInfo]:
        if self._available_models is None:
            self._available_models = discover_available_models()
        return self._available_models

    def _resolve_model(self, explicit: Optional[str], capability: str, preferences: list[tuple[str, str]]) -> tuple[str, str]:
        """
        Resolve which (provider, model) to use for a capability.

        Returns (provider_name, model_id).
        """
        if explicit:
            prov = self._provider_for_model(explicit)
            return prov, explicit

        if self.auto:
            # Try preference order, picking the first provider that has an API key
            for prov, model in preferences:
                try:
                    self._get_provider(prov)
                    return prov, model
                except (ValueError, ImportError):
                    continue

        raise RuntimeError(
            f"No provider available for capability '{capability}'. "
            "Set an API key for at least one provider."
        )

    def _track(self, provider: BaseProvider, prov_name: str, model: str) -> None:
        """Record usage from the last API call on a provider."""
        last = getattr(provider, "_last_usage", None)
        if last:
            self.usage.record(
                provider=prov_name,
                model=model,
                input_tokens=last.get("input_tokens", 0),
                output_tokens=last.get("output_tokens", 0),
            )
            provider._last_usage = None

    # --- Public API ---

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """Send a chat completion to the best available provider."""
        prov_name, model = self._resolve_model(self.chat_model, "chat", _CHAT_PREFERENCES)
        logger.info(f"Chat: using {prov_name}/{model}")
        provider = self._get_provider(prov_name)
        result = provider.chat(messages, max_tokens=max_tokens, temperature=temperature, model=model)
        self._track(provider, prov_name, model)
        return result

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 4096,
    ) -> str:
        """Analyze an image using the best available vision provider."""
        prov_name, model = self._resolve_model(self.vision_model, "vision", _VISION_PREFERENCES)
        logger.info(f"Vision: using {prov_name}/{model}")
        provider = self._get_provider(prov_name)
        result = provider.analyze_image(image_bytes, prompt, max_tokens=max_tokens, model=model)
        self._track(provider, prov_name, model)
        return result

    def transcribe_audio(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
    ) -> dict:
        """Transcribe audio using local Whisper if available, otherwise API."""
        # Prefer local Whisper — no file size limits, no API costs
        if not self.transcription_model or self.transcription_model.startswith("whisper-local"):
            try:
                from video_processor.providers.whisper_local import WhisperLocal

                if WhisperLocal.is_available():
                    # Parse model size from "whisper-local:large" or default to "large"
                    size = "large"
                    if self.transcription_model and ":" in self.transcription_model:
                        size = self.transcription_model.split(":", 1)[1]
                    if not hasattr(self, "_whisper_local"):
                        self._whisper_local = WhisperLocal(model_size=size)
                    logger.info(f"Transcription: using local whisper-{size}")
                    result = self._whisper_local.transcribe(audio_path, language=language)
                    duration = result.get("duration") or 0
                    self.usage.record(
                        provider="local",
                        model=f"whisper-{size}",
                        audio_minutes=duration / 60 if duration else 0,
                    )
                    return result
            except ImportError:
                pass

        # Fall back to API-based transcription
        prov_name, model = self._resolve_model(
            self.transcription_model, "audio", _TRANSCRIPTION_PREFERENCES
        )
        logger.info(f"Transcription: using {prov_name}/{model}")
        provider = self._get_provider(prov_name)
        result = provider.transcribe_audio(audio_path, language=language, model=model)
        duration = result.get("duration") or 0
        self.usage.record(
            provider=prov_name,
            model=model,
            audio_minutes=duration / 60 if duration else 0,
        )
        return result

    def get_models_used(self) -> dict[str, str]:
        """Return a dict mapping capability to 'provider/model' for tracking."""
        result = {}
        for cap, explicit, prefs in [
            ("vision", self.vision_model, _VISION_PREFERENCES),
            ("chat", self.chat_model, _CHAT_PREFERENCES),
            ("transcription", self.transcription_model, _TRANSCRIPTION_PREFERENCES),
        ]:
            try:
                prov, model = self._resolve_model(explicit, cap, prefs)
                result[cap] = f"{prov}/{model}"
            except RuntimeError:
                pass
        return result
