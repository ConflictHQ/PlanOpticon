"""OpenAI provider implementation."""

import base64
import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

from video_processor.providers.base import BaseProvider, ModelInfo

load_dotenv()
logger = logging.getLogger(__name__)

# Models known to have vision capability
_VISION_MODELS = {"gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "o1", "o3", "o3-mini", "o4-mini"}
_AUDIO_MODELS = {"whisper-1"}


class OpenAIProvider(BaseProvider):
    """OpenAI API provider."""

    provider_name = "openai"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")
        self.client = OpenAI(api_key=self.api_key)

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        model = model or "gpt-4o"
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> str:
        model = model or "gpt-4o"
        b64 = base64.b64encode(image_bytes).decode()
        response = self.client.chat.completions.create(
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
        return response.choices[0].message.content or ""

    def transcribe_audio(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        model = model or "whisper-1"
        with open(audio_path, "rb") as f:
            kwargs = {"model": model, "file": f}
            if language:
                kwargs["language"] = language
            response = self.client.audio.transcriptions.create(
                **kwargs, response_format="verbose_json"
            )
        return {
            "text": response.text,
            "segments": [
                {
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                }
                for seg in (response.segments or [])
            ],
            "language": getattr(response, "language", language),
            "duration": getattr(response, "duration", None),
            "provider": "openai",
            "model": model,
        }

    def list_models(self) -> list[ModelInfo]:
        models = []
        try:
            for m in self.client.models.list():
                mid = m.id
                caps = []
                # Infer capabilities from model id
                if any(mid.startswith(p) for p in ("gpt-", "o1", "o3", "o4")):
                    caps.append("chat")
                if any(v in mid for v in _VISION_MODELS) or "gpt-4o" in mid or "gpt-4.1" in mid:
                    caps.append("vision")
                if mid in _AUDIO_MODELS or mid.startswith("whisper"):
                    caps.append("audio")
                if "embedding" in mid:
                    caps.append("embedding")
                if caps:
                    models.append(ModelInfo(
                        id=mid,
                        provider="openai",
                        display_name=mid,
                        capabilities=caps,
                    ))
        except Exception as e:
            logger.warning(f"Failed to list OpenAI models: {e}")
        return sorted(models, key=lambda m: m.id)
