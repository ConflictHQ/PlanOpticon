"""Ollama provider implementation using OpenAI-compatible API."""

import base64
import logging
import os
from pathlib import Path
from typing import Optional

import requests
from openai import OpenAI

from video_processor.providers.base import BaseProvider, ModelInfo

logger = logging.getLogger(__name__)

# Known vision-capable model families (base name before the colon/tag)
_VISION_FAMILIES = {
    "llava",
    "llava-llama3",
    "llava-phi3",
    "llama3.2-vision",
    "moondream",
    "bakllava",
    "minicpm-v",
    "deepseek-vl",
    "internvl2",
}

DEFAULT_HOST = "http://localhost:11434"


class OllamaProvider(BaseProvider):
    """Ollama local LLM provider via OpenAI-compatible API."""

    provider_name = "ollama"

    def __init__(self, host: Optional[str] = None):
        self.host = host or os.getenv("OLLAMA_HOST", DEFAULT_HOST)
        self.client = OpenAI(
            base_url=f"{self.host}/v1",
            api_key="ollama",
        )
        self._models_cache: Optional[list[ModelInfo]] = None

    @staticmethod
    def is_available(host: Optional[str] = None) -> bool:
        """Check if an Ollama server is running and reachable."""
        host = host or os.getenv("OLLAMA_HOST", DEFAULT_HOST)
        try:
            resp = requests.get(f"{host}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    @property
    def _default_model(self) -> str:
        models = self._get_models()
        for m in models:
            if "chat" in m.capabilities:
                return m.id
        return "llama3.2:latest"

    @property
    def _default_vision_model(self) -> Optional[str]:
        models = self._get_models()
        for m in models:
            if "vision" in m.capabilities:
                return m.id
        return None

    def _get_models(self) -> list[ModelInfo]:
        if self._models_cache is None:
            self._models_cache = self.list_models()
        return self._models_cache

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        model = model or self._default_model
        response = self.client.chat.completions.create(
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
        model = model or self._default_vision_model
        if not model:
            raise RuntimeError(
                "No Ollama vision model available. Install a multimodal model: ollama pull llava"
            )
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
            "Ollama does not support audio transcription. "
            "Use local Whisper (--transcription-model whisper-local:large) or OpenAI Whisper API."
        )

    def list_models(self) -> list[ModelInfo]:
        models = []
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            for m in data.get("models", []):
                name = m.get("name", "")
                caps = ["chat"]
                base_name = name.split(":")[0].lower()
                if base_name in _VISION_FAMILIES or "vision" in base_name:
                    caps.append("vision")
                models.append(
                    ModelInfo(
                        id=name,
                        provider="ollama",
                        display_name=name,
                        capabilities=caps,
                    )
                )
        except Exception as e:
            logger.warning(f"Failed to list Ollama models: {e}")
        return sorted(models, key=lambda m: m.id)
