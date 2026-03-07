"""Cohere provider implementation."""

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from video_processor.providers.base import BaseProvider, ModelInfo, ProviderRegistry

load_dotenv()
logger = logging.getLogger(__name__)

# Curated list of Cohere models
_COHERE_MODELS = [
    ModelInfo(
        id="command-r-plus",
        provider="cohere",
        display_name="Command R+",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="command-r",
        provider="cohere",
        display_name="Command R",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="command-light",
        provider="cohere",
        display_name="Command Light",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="command-nightly",
        provider="cohere",
        display_name="Command Nightly",
        capabilities=["chat"],
    ),
]


class CohereProvider(BaseProvider):
    """Cohere provider using the cohere SDK."""

    provider_name = "cohere"

    def __init__(self, api_key: Optional[str] = None):
        try:
            import cohere
        except ImportError:
            raise ImportError("cohere package not installed. Install with: pip install cohere")

        self._api_key = api_key or os.getenv("COHERE_API_KEY")
        if not self._api_key:
            raise ValueError("COHERE_API_KEY not set")

        self._client = cohere.ClientV2(api_key=self._api_key)
        self._last_usage = {}

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        model = model or "command-r-plus"

        response = self._client.chat(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        usage = getattr(response, "usage", None)
        tokens = getattr(usage, "tokens", None) if usage else None
        self._last_usage = {
            "input_tokens": getattr(tokens, "input_tokens", 0) if tokens else 0,
            "output_tokens": getattr(tokens, "output_tokens", 0) if tokens else 0,
        }
        return response.message.content[0].text if response.message.content else ""

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> str:
        raise NotImplementedError(
            "Cohere does not currently support vision/image analysis. "
            "Use OpenAI, Anthropic, or Gemini for image analysis."
        )

    def transcribe_audio(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        raise NotImplementedError(
            "Cohere does not provide a transcription API. "
            "Use OpenAI Whisper or Gemini for transcription."
        )

    def list_models(self) -> list[ModelInfo]:
        return list(_COHERE_MODELS)


ProviderRegistry.register(
    name="cohere",
    provider_class=CohereProvider,
    env_var="COHERE_API_KEY",
    model_prefixes=["command-"],
    default_models={
        "chat": "command-r-plus",
        "vision": "",
        "audio": "",
    },
)
