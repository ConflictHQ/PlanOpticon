"""Fireworks AI provider implementation."""

from video_processor.providers.base import OpenAICompatibleProvider, ProviderRegistry


class FireworksProvider(OpenAICompatibleProvider):
    """Fireworks AI API provider (OpenAI-compatible)."""

    provider_name = "fireworks"
    base_url = "https://api.fireworks.ai/inference/v1"
    env_var = "FIREWORKS_API_KEY"


ProviderRegistry.register(
    name="fireworks",
    provider_class=FireworksProvider,
    env_var="FIREWORKS_API_KEY",
    model_prefixes=["accounts/fireworks/"],
    default_models={
        "chat": "accounts/fireworks/models/llama-v3p1-70b-instruct",
        "vision": "",
        "audio": "",
    },
)
