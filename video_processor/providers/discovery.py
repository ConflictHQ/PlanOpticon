"""Auto-discover available models across providers."""

import logging
import os
from typing import Optional

from dotenv import load_dotenv

from video_processor.providers.base import ModelInfo, ProviderRegistry

load_dotenv()
logger = logging.getLogger(__name__)

_cached_models: Optional[list[ModelInfo]] = None


def _ensure_providers_registered() -> None:
    """Import all built-in provider modules so they register themselves."""
    if ProviderRegistry.all_registered():
        return
    import video_processor.providers.anthropic_provider  # noqa: F401
    import video_processor.providers.gemini_provider  # noqa: F401
    import video_processor.providers.ollama_provider  # noqa: F401
    import video_processor.providers.openai_provider  # noqa: F401


def discover_available_models(
    api_keys: Optional[dict[str, str]] = None,
    force_refresh: bool = False,
) -> list[ModelInfo]:
    """
    Discover available models from all configured providers.

    For each provider with a valid API key, calls list_models() and returns
    a unified list. Results are cached for the session.
    """
    global _cached_models
    if _cached_models is not None and not force_refresh:
        return _cached_models

    _ensure_providers_registered()

    keys = api_keys or {
        "openai": os.getenv("OPENAI_API_KEY", ""),
        "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
        "gemini": os.getenv("GEMINI_API_KEY", ""),
    }

    all_models: list[ModelInfo] = []

    for name, info in ProviderRegistry.all_registered().items():
        env_var = info.get("env_var", "")
        provider_class = info["class"]

        if name == "ollama":
            # Ollama: no API key, check server availability
            try:
                if provider_class.is_available():
                    provider = provider_class()
                    models = provider.list_models()
                    logger.info(f"Discovered {len(models)} Ollama models")
                    all_models.extend(models)
            except Exception as e:
                logger.info(f"Ollama discovery skipped: {e}")
            continue

        # For key-based providers, check the api_keys dict first, then env var
        key = keys.get(name, "")
        if not key and env_var:
            key = os.getenv(env_var, "")

        # Special case: Gemini also supports service account credentials
        gemini_creds = ""
        if name == "gemini":
            gemini_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

        if not key and not gemini_creds:
            continue

        try:
            # Handle provider-specific constructor args
            if name == "gemini":
                provider = provider_class(
                    api_key=key or None,
                    credentials_path=gemini_creds or None,
                )
            else:
                provider = provider_class(api_key=key)
            models = provider.list_models()
            logger.info(f"Discovered {len(models)} {name.capitalize()} models")
            all_models.extend(models)
        except Exception as e:
            logger.info(f"{name.capitalize()} discovery skipped: {e}")

    # Sort by provider then id
    all_models.sort(key=lambda m: (m.provider, m.id))
    _cached_models = all_models
    logger.info(f"Total discovered models: {len(all_models)}")
    return all_models


def clear_discovery_cache() -> None:
    """Clear the cached model list."""
    global _cached_models
    _cached_models = None
