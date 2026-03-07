"""Azure OpenAI provider implementation."""

import os

from video_processor.providers.base import OpenAICompatibleProvider, ProviderRegistry


class AzureOpenAIProvider(OpenAICompatibleProvider):
    """Azure OpenAI API provider.

    Uses the AzureOpenAI client which requires an endpoint and API version
    in addition to the API key.
    """

    provider_name = "azure"
    env_var = "AZURE_OPENAI_API_KEY"

    def __init__(self, api_key=None, endpoint=None, api_version=None):
        from openai import AzureOpenAI

        self._api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY", "")
        endpoint = endpoint or os.getenv("AZURE_OPENAI_ENDPOINT", "")
        api_version = api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        self._client = AzureOpenAI(
            api_key=self._api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        self._last_usage = None


ProviderRegistry.register(
    name="azure",
    provider_class=AzureOpenAIProvider,
    env_var="AZURE_OPENAI_API_KEY",
    model_prefixes=[],  # Azure uses deployment names, not standard prefixes
    default_models={"chat": "", "vision": "", "audio": ""},
)
