"""AI21 Labs provider implementation."""

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from video_processor.providers.base import ModelInfo, OpenAICompatibleProvider, ProviderRegistry

load_dotenv()
logger = logging.getLogger(__name__)

# Curated list of AI21 models
_AI21_MODELS = [
    ModelInfo(
        id="jamba-1.5-large",
        provider="ai21",
        display_name="Jamba 1.5 Large",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="jamba-1.5-mini",
        provider="ai21",
        display_name="Jamba 1.5 Mini",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="jamba-instruct",
        provider="ai21",
        display_name="Jamba Instruct",
        capabilities=["chat"],
    ),
]


class AI21Provider(OpenAICompatibleProvider):
    """AI21 Labs provider using OpenAI-compatible API."""

    provider_name = "ai21"
    base_url = "https://api.ai21.com/studio/v1"
    env_var = "AI21_API_KEY"

    def __init__(self, api_key: Optional[str] = None):
        api_key = api_key or os.getenv("AI21_API_KEY")
        if not api_key:
            raise ValueError("AI21_API_KEY not set")
        super().__init__(api_key=api_key, base_url=self.base_url)

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        model = model or "jamba-1.5-large"
        return super().chat(messages, max_tokens, temperature, model)

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> str:
        raise NotImplementedError(
            "AI21 does not currently support vision/image analysis. "
            "Use OpenAI, Anthropic, or Gemini for image analysis."
        )

    def transcribe_audio(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        raise NotImplementedError(
            "AI21 does not provide a transcription API. "
            "Use OpenAI Whisper or Gemini for transcription."
        )

    def list_models(self) -> list[ModelInfo]:
        return list(_AI21_MODELS)


ProviderRegistry.register(
    name="ai21",
    provider_class=AI21Provider,
    env_var="AI21_API_KEY",
    model_prefixes=["jamba-", "j2-"],
    default_models={
        "chat": "jamba-1.5-large",
        "vision": "",
        "audio": "",
    },
)
