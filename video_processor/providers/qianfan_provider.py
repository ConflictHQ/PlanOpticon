"""Baidu Qianfan (ERNIE) provider implementation."""

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from video_processor.providers.base import BaseProvider, ModelInfo, ProviderRegistry

load_dotenv()
logger = logging.getLogger(__name__)

# Curated list of Qianfan models
_QIANFAN_MODELS = [
    ModelInfo(
        id="ernie-4.0-8k",
        provider="qianfan",
        display_name="ERNIE 4.0 8K",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="ernie-3.5-8k",
        provider="qianfan",
        display_name="ERNIE 3.5 8K",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="ernie-speed-8k",
        provider="qianfan",
        display_name="ERNIE Speed 8K",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="ernie-lite-8k",
        provider="qianfan",
        display_name="ERNIE Lite 8K",
        capabilities=["chat"],
    ),
]


class QianfanProvider(BaseProvider):
    """Baidu Qianfan provider using the qianfan SDK."""

    provider_name = "qianfan"

    def __init__(
        self,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
    ):
        try:
            import qianfan
        except ImportError:
            raise ImportError("qianfan package not installed. Install with: pip install qianfan")

        self._access_key = access_key or os.getenv("QIANFAN_ACCESS_KEY")
        self._secret_key = secret_key or os.getenv("QIANFAN_SECRET_KEY")

        if not self._access_key or not self._secret_key:
            raise ValueError("QIANFAN_ACCESS_KEY and QIANFAN_SECRET_KEY must both be set")

        # Set env vars for the SDK to pick up
        os.environ["QIANFAN_ACCESS_KEY"] = self._access_key
        os.environ["QIANFAN_SECRET_KEY"] = self._secret_key

        self._qianfan = qianfan
        self._last_usage = {}

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        model = model or "ernie-4.0-8k"
        if model.startswith("qianfan/"):
            model = model[len("qianfan/") :]

        chat_comp = self._qianfan.ChatCompletion()
        response = chat_comp.do(
            model=model,
            messages=messages,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        body = response.get("body", response) if hasattr(response, "get") else response
        usage = body.get("usage", {}) if hasattr(body, "get") else {}
        self._last_usage = {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }

        result = body.get("result", "") if hasattr(body, "get") else str(body)
        return result

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> str:
        raise NotImplementedError(
            "Qianfan image analysis is not supported in this provider. "
            "Use OpenAI, Anthropic, or Gemini for image analysis."
        )

    def transcribe_audio(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        raise NotImplementedError(
            "Qianfan does not provide a transcription API through this provider. "
            "Use OpenAI Whisper or Gemini for transcription."
        )

    def list_models(self) -> list[ModelInfo]:
        return list(_QIANFAN_MODELS)


ProviderRegistry.register(
    name="qianfan",
    provider_class=QianfanProvider,
    env_var="QIANFAN_ACCESS_KEY",
    model_prefixes=["ernie-", "qianfan/"],
    default_models={
        "chat": "ernie-4.0-8k",
        "vision": "",
        "audio": "",
    },
)
