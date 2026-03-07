"""Mistral AI provider implementation."""

import base64
import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from video_processor.providers.base import BaseProvider, ModelInfo, ProviderRegistry

load_dotenv()
logger = logging.getLogger(__name__)

# Curated list of Mistral models
_MISTRAL_MODELS = [
    ModelInfo(
        id="mistral-large-latest",
        provider="mistral",
        display_name="Mistral Large",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="mistral-medium-latest",
        provider="mistral",
        display_name="Mistral Medium",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="mistral-small-latest",
        provider="mistral",
        display_name="Mistral Small",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="open-mistral-nemo",
        provider="mistral",
        display_name="Mistral Nemo",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="pixtral-large-latest",
        provider="mistral",
        display_name="Pixtral Large",
        capabilities=["chat", "vision"],
    ),
    ModelInfo(
        id="pixtral-12b-2409",
        provider="mistral",
        display_name="Pixtral 12B",
        capabilities=["chat", "vision"],
    ),
    ModelInfo(
        id="codestral-latest",
        provider="mistral",
        display_name="Codestral",
        capabilities=["chat"],
    ),
]


class MistralProvider(BaseProvider):
    """Mistral AI provider using the mistralai SDK."""

    provider_name = "mistral"

    def __init__(self, api_key: Optional[str] = None):
        try:
            from mistralai import Mistral
        except ImportError:
            raise ImportError(
                "mistralai package not installed. Install with: pip install mistralai"
            )

        self._api_key = api_key or os.getenv("MISTRAL_API_KEY")
        if not self._api_key:
            raise ValueError("MISTRAL_API_KEY not set")

        self._client = Mistral(api_key=self._api_key)
        self._last_usage = {}

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        model = model or "mistral-large-latest"

        response = self._client.chat.complete(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        self._last_usage = {
            "input_tokens": getattr(response.usage, "prompt_tokens", 0) if response.usage else 0,
            "output_tokens": getattr(response.usage, "completion_tokens", 0)
            if response.usage
            else 0,
        }
        return response.choices[0].message.content or ""

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> str:
        model = model or "pixtral-large-latest"
        b64 = base64.b64encode(image_bytes).decode()

        response = self._client.chat.complete(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                }
            ],
            max_tokens=max_tokens,
        )

        self._last_usage = {
            "input_tokens": getattr(response.usage, "prompt_tokens", 0) if response.usage else 0,
            "output_tokens": getattr(response.usage, "completion_tokens", 0)
            if response.usage
            else 0,
        }
        return response.choices[0].message.content or ""

    def transcribe_audio(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        raise NotImplementedError(
            "Mistral does not provide a transcription API. "
            "Use OpenAI Whisper or Gemini for transcription."
        )

    def list_models(self) -> list[ModelInfo]:
        return list(_MISTRAL_MODELS)


ProviderRegistry.register(
    name="mistral",
    provider_class=MistralProvider,
    env_var="MISTRAL_API_KEY",
    model_prefixes=["mistral-", "pixtral-", "codestral-", "open-mistral-"],
    default_models={
        "chat": "mistral-large-latest",
        "vision": "pixtral-large-latest",
        "audio": "",
    },
)
