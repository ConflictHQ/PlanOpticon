"""Cerebras provider implementation."""

from video_processor.providers.base import OpenAICompatibleProvider, ProviderRegistry


class CerebrasProvider(OpenAICompatibleProvider):
    """Cerebras AI API provider (OpenAI-compatible)."""

    provider_name = "cerebras"
    base_url = "https://api.cerebras.ai/v1"
    env_var = "CEREBRAS_API_KEY"


ProviderRegistry.register(
    name="cerebras",
    provider_class=CerebrasProvider,
    env_var="CEREBRAS_API_KEY",
    model_prefixes=["cerebras/"],
    default_models={"chat": "llama3.1-70b", "vision": "", "audio": ""},
)
