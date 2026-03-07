"""Abstract base class, registry, and shared types for provider implementations."""

import base64
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ModelInfo(BaseModel):
    """Information about an available model."""

    id: str = Field(description="Model identifier (e.g. gpt-4o)")
    provider: str = Field(description="Provider name (openai, anthropic, gemini)")
    display_name: str = Field(default="", description="Human-readable name")
    capabilities: List[str] = Field(
        default_factory=list, description="Model capabilities: chat, vision, audio, embedding"
    )


class BaseProvider(ABC):
    """Abstract base for all provider implementations."""

    provider_name: str = ""

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        """Send a chat completion request. Returns the assistant text."""

    @abstractmethod
    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> str:
        """Analyze an image with a prompt. Returns the assistant text."""

    @abstractmethod
    def transcribe_audio(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        """Transcribe an audio file. Returns dict with 'text', 'segments', etc."""

    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """Discover available models from this provider's API."""


class ProviderRegistry:
    """Registry for provider classes. Providers register themselves with metadata."""

    _providers: Dict[str, Dict] = {}

    @classmethod
    def register(
        cls,
        name: str,
        provider_class: type,
        env_var: str = "",
        model_prefixes: Optional[List[str]] = None,
        default_models: Optional[Dict[str, str]] = None,
    ) -> None:
        """Register a provider class with its metadata."""
        cls._providers[name] = {
            "class": provider_class,
            "env_var": env_var,
            "model_prefixes": model_prefixes or [],
            "default_models": default_models or {},
        }

    @classmethod
    def get(cls, name: str) -> type:
        """Return the provider class for a given name."""
        if name not in cls._providers:
            raise ValueError(f"Unknown provider: {name}")
        return cls._providers[name]["class"]

    @classmethod
    def get_by_model(cls, model_id: str) -> Optional[str]:
        """Return provider name for a model ID based on prefix matching."""
        for name, info in cls._providers.items():
            for prefix in info["model_prefixes"]:
                if model_id.startswith(prefix):
                    return name
        return None

    @classmethod
    def get_default_models(cls, name: str) -> Dict[str, str]:
        """Return the default models dict for a provider."""
        if name not in cls._providers:
            return {}
        return cls._providers[name].get("default_models", {})

    @classmethod
    def available(cls) -> List[str]:
        """Return names of providers whose env var is set (or have no env var requirement)."""
        result = []
        for name, info in cls._providers.items():
            env_var = info.get("env_var", "")
            if not env_var:
                # Providers without an env var (e.g. ollama) need special availability checks
                result.append(name)
            elif os.getenv(env_var, ""):
                result.append(name)
        return result

    @classmethod
    def all_registered(cls) -> Dict[str, Dict]:
        """Return all registered providers and their metadata."""
        return dict(cls._providers)


class OpenAICompatibleProvider(BaseProvider):
    """Base for providers using OpenAI-compatible APIs.

    Suitable for Together, Fireworks, Cerebras, xAI, Azure, and similar services.
    """

    provider_name: str = ""
    base_url: str = ""
    env_var: str = ""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        from openai import OpenAI

        self._api_key = api_key or os.getenv(self.env_var, "")
        self._base_url = base_url or self.base_url
        self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        self._last_usage = None

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        model = model or "gpt-4o"
        response = self._client.chat.completions.create(
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
        model = model or "gpt-4o"
        b64 = base64.b64encode(image_bytes).decode()
        response = self._client.chat.completions.create(
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
        raise NotImplementedError(f"{self.provider_name} does not support audio transcription")

    def list_models(self) -> list[ModelInfo]:
        models = []
        try:
            for m in self._client.models.list():
                mid = m.id
                caps = ["chat"]
                models.append(
                    ModelInfo(
                        id=mid,
                        provider=self.provider_name,
                        display_name=mid,
                        capabilities=caps,
                    )
                )
        except Exception as e:
            logger.warning(f"Failed to list {self.provider_name} models: {e}")
        return sorted(models, key=lambda m: m.id)
