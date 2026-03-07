"""xAI (Grok) provider implementation."""

from video_processor.providers.base import OpenAICompatibleProvider, ProviderRegistry


class XAIProvider(OpenAICompatibleProvider):
    """xAI API provider (OpenAI-compatible)."""

    provider_name = "xai"
    base_url = "https://api.x.ai/v1"
    env_var = "XAI_API_KEY"


ProviderRegistry.register(
    name="xai",
    provider_class=XAIProvider,
    env_var="XAI_API_KEY",
    model_prefixes=["grok-"],
    default_models={"chat": "grok-2", "vision": "grok-2-vision", "audio": ""},
)
