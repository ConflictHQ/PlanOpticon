"""Auto-discover available models across providers."""

import logging
import os
from typing import Optional

from dotenv import load_dotenv

from video_processor.providers.base import ModelInfo

load_dotenv()
logger = logging.getLogger(__name__)

_cached_models: Optional[list[ModelInfo]] = None


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

    keys = api_keys or {
        "openai": os.getenv("OPENAI_API_KEY", ""),
        "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
        "gemini": os.getenv("GEMINI_API_KEY", ""),
    }

    all_models: list[ModelInfo] = []

    # OpenAI
    if keys.get("openai"):
        try:
            from video_processor.providers.openai_provider import OpenAIProvider

            provider = OpenAIProvider(api_key=keys["openai"])
            models = provider.list_models()
            logger.info(f"Discovered {len(models)} OpenAI models")
            all_models.extend(models)
        except Exception as e:
            logger.info(f"OpenAI discovery skipped: {e}")

    # Anthropic
    if keys.get("anthropic"):
        try:
            from video_processor.providers.anthropic_provider import AnthropicProvider

            provider = AnthropicProvider(api_key=keys["anthropic"])
            models = provider.list_models()
            logger.info(f"Discovered {len(models)} Anthropic models")
            all_models.extend(models)
        except Exception as e:
            logger.info(f"Anthropic discovery skipped: {e}")

    # Gemini (API key or service account)
    gemini_key = keys.get("gemini")
    gemini_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    if gemini_key or gemini_creds:
        try:
            from video_processor.providers.gemini_provider import GeminiProvider

            provider = GeminiProvider(
                api_key=gemini_key or None,
                credentials_path=gemini_creds or None,
            )
            models = provider.list_models()
            logger.info(f"Discovered {len(models)} Gemini models")
            all_models.extend(models)
        except Exception as e:
            logger.warning(f"Gemini discovery failed: {e}")

    # Sort by provider then id
    all_models.sort(key=lambda m: (m.provider, m.id))
    _cached_models = all_models
    logger.info(f"Total discovered models: {len(all_models)}")
    return all_models


def clear_discovery_cache() -> None:
    """Clear the cached model list."""
    global _cached_models
    _cached_models = None
