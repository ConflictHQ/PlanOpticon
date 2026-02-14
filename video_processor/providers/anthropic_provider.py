"""Anthropic provider implementation."""

import base64
import logging
import os
from pathlib import Path
from typing import Optional

import anthropic
from dotenv import load_dotenv

from video_processor.providers.base import BaseProvider, ModelInfo

load_dotenv()
logger = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    """Anthropic Claude API provider."""

    provider_name = "anthropic"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        model = model or "claude-sonnet-4-5-20250929"
        response = self.client.messages.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.content[0].text

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> str:
        model = model or "claude-sonnet-4-5-20250929"
        b64 = base64.b64encode(image_bytes).decode()
        response = self.client.messages.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            max_tokens=max_tokens,
        )
        return response.content[0].text

    def transcribe_audio(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        raise NotImplementedError(
            "Anthropic does not provide a dedicated transcription API. "
            "Use OpenAI Whisper or Gemini for transcription."
        )

    def list_models(self) -> list[ModelInfo]:
        models = []
        try:
            page = self.client.models.list(limit=100)
            for m in page.data:
                mid = m.id
                caps = ["chat", "vision"]  # All Claude models support chat + vision
                models.append(ModelInfo(
                    id=mid,
                    provider="anthropic",
                    display_name=getattr(m, "display_name", mid),
                    capabilities=caps,
                ))
        except Exception as e:
            logger.warning(f"Failed to list Anthropic models: {e}")
        return sorted(models, key=lambda m: m.id)
