"""Together AI provider implementation."""

from video_processor.providers.base import OpenAICompatibleProvider, ProviderRegistry


class TogetherProvider(OpenAICompatibleProvider):
    """Together AI API provider (OpenAI-compatible)."""

    provider_name = "together"
    base_url = "https://api.together.xyz/v1"
    env_var = "TOGETHER_API_KEY"


ProviderRegistry.register(
    name="together",
    provider_class=TogetherProvider,
    env_var="TOGETHER_API_KEY",
    model_prefixes=["together/", "meta-llama/", "mistralai/", "Qwen/"],
    default_models={"chat": "meta-llama/Llama-3-70b-chat-hf", "vision": "", "audio": ""},
)
