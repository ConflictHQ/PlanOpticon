"""ProviderManager - unified interface for routing API calls to the best available provider."""

import inspect
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from video_processor.providers.base import BaseProvider, ModelInfo, ProviderRegistry
from video_processor.providers.discovery import discover_available_models
from video_processor.utils.usage_tracker import UsageTracker

load_dotenv()
logger = logging.getLogger(__name__)


_BUILTINS_REGISTERED = False


def _ensure_providers_registered() -> None:
    """Import all built-in provider modules so they register themselves.

    Guarded by a module flag rather than the registry contents: a single
    provider module imported elsewhere first would otherwise make this
    short-circuit and skip the rest. Imports are cached, so this is cheap.
    """
    global _BUILTINS_REGISTERED
    if _BUILTINS_REGISTERED:
        return
    _BUILTINS_REGISTERED = True
    # Each module registers itself on import via ProviderRegistry.register()
    import video_processor.providers.anthropic_provider  # noqa: F401
    import video_processor.providers.azure_provider  # noqa: F401
    import video_processor.providers.cerebras_provider  # noqa: F401
    import video_processor.providers.deepgram_provider  # noqa: F401
    import video_processor.providers.elevenlabs_provider  # noqa: F401
    import video_processor.providers.fireworks_provider  # noqa: F401
    import video_processor.providers.gemini_provider  # noqa: F401
    import video_processor.providers.ollama_provider  # noqa: F401
    import video_processor.providers.openai_provider  # noqa: F401
    import video_processor.providers.together_provider  # noqa: F401
    import video_processor.providers.xai_provider  # noqa: F401


def _accepts_speaker_hints(provider: BaseProvider) -> bool:
    """Check whether a provider's transcribe_audio() accepts a speaker_hints kwarg."""
    try:
        params = inspect.signature(provider.transcribe_audio).parameters
    except (TypeError, ValueError):
        return False
    return "speaker_hints" in params or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
    )


# Default model preference rankings (tried in order)
_VISION_PREFERENCES = [
    ("gemini", "gemini-2.5-flash"),
    ("openai", "gpt-4o-mini"),
    ("anthropic", "claude-haiku-4-5-20251001"),
]

_CHAT_PREFERENCES = [
    ("anthropic", "claude-haiku-4-5-20251001"),
    ("openai", "gpt-4o-mini"),
    ("gemini", "gemini-2.5-flash"),
]

_TRANSCRIPTION_PREFERENCES = [
    ("openai", "whisper-1"),
    ("gemini", "gemini-2.5-flash"),
]

# Diarization-capable transcribers, tried in order when --diarize is requested
# without an explicit transcriber. Deepgram first (fastest/cheapest).
_DIARIZATION_PREFERENCES = [
    ("deepgram", "nova-3"),
    ("elevenlabs", "scribe_v1"),
]
_DIARIZE_CAPABLE = {"deepgram", "elevenlabs"}


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
        _ensure_providers_registered()
        self.auto = auto
        self._providers: dict[str, BaseProvider] = {}
        self._available_models: Optional[list[ModelInfo]] = None
        self.usage = UsageTracker()

        # If a single provider is forced, apply it
        if provider:
            self.vision_model = vision_model or self._default_for_provider(provider, "vision")
            self.chat_model = chat_model or self._default_for_provider(provider, "chat")
            self.transcription_model = transcription_model or self._default_for_provider(
                provider, "audio"
            )
        else:
            self.vision_model = vision_model
            self.chat_model = chat_model
            self.transcription_model = transcription_model

        self._forced_provider = provider

    @staticmethod
    def _default_for_provider(provider: str, capability: str) -> str:
        """Return the default model for a provider/capability combo."""
        defaults = ProviderRegistry.get_default_models(provider)
        if defaults:
            return defaults.get(capability, "")
        # Fallback for unregistered providers
        return ""

    def _get_provider(self, provider_name: str) -> BaseProvider:
        """Lazily initialize and cache a provider instance."""
        if provider_name not in self._providers:
            _ensure_providers_registered()
            provider_class = ProviderRegistry.get(provider_name)
            self._providers[provider_name] = provider_class()
        return self._providers[provider_name]

    def _provider_for_model(self, model_id: str) -> str:
        """Infer the provider from a model id."""
        _ensure_providers_registered()
        # Check registry prefix matching first
        provider_name = ProviderRegistry.get_by_model(model_id)
        if provider_name:
            return provider_name
        # Try discovery (exact match, then prefix match for ollama name:tag format)
        models = self._get_available_models()
        for m in models:
            if m.id == model_id:
                return m.provider
        for m in models:
            if m.id.startswith(model_id + ":"):
                return m.provider
        raise ValueError(f"Cannot determine provider for model: {model_id}")

    def _get_available_models(self) -> list[ModelInfo]:
        if self._available_models is None:
            self._available_models = discover_available_models()
        return self._available_models

    def _resolve_model(
        self, explicit: Optional[str], capability: str, preferences: list[tuple[str, str]]
    ) -> tuple[str, str]:
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

            # Fallback: try Ollama if available (no API key needed)
            try:
                from video_processor.providers.ollama_provider import OllamaProvider

                if OllamaProvider.is_available():
                    provider = self._get_provider("ollama")
                    models = provider.list_models()
                    for m in models:
                        if capability in m.capabilities:
                            return "ollama", m.id
            except Exception:
                pass

        raise RuntimeError(
            f"No provider available for capability '{capability}'. "
            "Set an API key for at least one provider, or start Ollama."
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
        result = provider.chat(
            messages, max_tokens=max_tokens, temperature=temperature, model=model
        )
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
        speaker_hints: Optional[list[str]] = None,
        diarize: bool = False,
    ) -> dict:
        """Transcribe audio. With diarize=True, route to a speaker-labeling
        provider (Deepgram/ElevenLabs); otherwise prefer local Whisper, then API."""
        # Diarization path: only Deepgram/ElevenLabs populate segment speakers.
        if diarize:
            prov_name, model = self._resolve_model(
                self.transcription_model, "audio", _DIARIZATION_PREFERENCES
            )
            if prov_name in _DIARIZE_CAPABLE:
                logger.info(f"Transcription (diarized): using {prov_name}/{model}")
                provider = self._get_provider(prov_name)
                kwargs: dict = {"language": language, "model": model, "diarize": True}
                if speaker_hints:
                    kwargs["speaker_hints"] = speaker_hints
                result = provider.transcribe_audio(audio_path, **kwargs)
                duration = result.get("duration") or 0
                self.usage.record(
                    provider=prov_name,
                    model=model,
                    audio_minutes=duration / 60 if duration else 0,
                )
                return result
            logger.warning(
                f"Transcriber '{prov_name}' does not support diarization; "
                "transcribing without speaker labels."
            )

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
                    # Pass speaker names as initial prompt hint for Whisper
                    whisper_kwargs = {"language": language}
                    if speaker_hints:
                        whisper_kwargs["initial_prompt"] = (
                            "Speakers: " + ", ".join(speaker_hints) + "."
                        )
                    result = self._whisper_local.transcribe(audio_path, **whisper_kwargs)
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
        # Build transcription kwargs, passing speaker hints where supported
        transcribe_kwargs: dict = {"language": language, "model": model}
        if speaker_hints:
            if prov_name == "openai":
                # OpenAI Whisper supports a 'prompt' parameter for hints
                transcribe_kwargs["prompt"] = "Speakers: " + ", ".join(speaker_hints) + "."
            elif _accepts_speaker_hints(provider):
                transcribe_kwargs["speaker_hints"] = speaker_hints
            else:
                logger.warning(
                    f"Transcriber '{prov_name}' does not support speaker hints; ignoring."
                )
        result = provider.transcribe_audio(audio_path, **transcribe_kwargs)
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
