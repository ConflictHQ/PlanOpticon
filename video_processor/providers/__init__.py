"""Provider abstraction layer for LLM, vision, and transcription APIs."""

from video_processor.providers.base import (
    BaseProvider,
    ModelInfo,
    OpenAICompatibleProvider,
    ProviderRegistry,
)
from video_processor.providers.manager import ProviderManager

__all__ = [
    "BaseProvider",
    "ModelInfo",
    "OpenAICompatibleProvider",
    "ProviderManager",
    "ProviderRegistry",
    # OpenAI-compatible providers (lazy-loaded via manager)
    "AzureOpenAIProvider",
    "CerebrasProvider",
    "FireworksProvider",
    "TogetherProvider",
    "XAIProvider",
]


def __getattr__(name: str):
    """Lazy import provider classes to avoid import-time side effects."""
    _lazy_imports = {
        "AzureOpenAIProvider": "video_processor.providers.azure_provider",
        "CerebrasProvider": "video_processor.providers.cerebras_provider",
        "FireworksProvider": "video_processor.providers.fireworks_provider",
        "TogetherProvider": "video_processor.providers.together_provider",
        "XAIProvider": "video_processor.providers.xai_provider",
    }
    if name in _lazy_imports:
        import importlib

        mod = importlib.import_module(_lazy_imports[name])
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
