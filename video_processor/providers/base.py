"""Abstract base class and shared types for provider implementations."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class ModelInfo(BaseModel):
    """Information about an available model."""
    id: str = Field(description="Model identifier (e.g. gpt-4o)")
    provider: str = Field(description="Provider name (openai, anthropic, gemini)")
    display_name: str = Field(default="", description="Human-readable name")
    capabilities: List[str] = Field(
        default_factory=list,
        description="Model capabilities: chat, vision, audio, embedding"
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
