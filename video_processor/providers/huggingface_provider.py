"""Hugging Face Inference API provider implementation."""

import base64
import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from video_processor.providers.base import BaseProvider, ModelInfo, ProviderRegistry

load_dotenv()
logger = logging.getLogger(__name__)

# Curated list of popular HF Inference models
_HF_MODELS = [
    ModelInfo(
        id="meta-llama/Llama-3.1-70B-Instruct",
        provider="huggingface",
        display_name="Llama 3.1 70B Instruct",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="meta-llama/Llama-3.1-8B-Instruct",
        provider="huggingface",
        display_name="Llama 3.1 8B Instruct",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="mistralai/Mixtral-8x7B-Instruct-v0.1",
        provider="huggingface",
        display_name="Mixtral 8x7B Instruct",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="microsoft/Phi-3-mini-4k-instruct",
        provider="huggingface",
        display_name="Phi-3 Mini 4K Instruct",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="llava-hf/llava-v1.6-mistral-7b-hf",
        provider="huggingface",
        display_name="LLaVA v1.6 Mistral 7B",
        capabilities=["chat", "vision"],
    ),
    ModelInfo(
        id="openai/whisper-large-v3",
        provider="huggingface",
        display_name="Whisper Large v3",
        capabilities=["audio"],
    ),
]


class HuggingFaceProvider(BaseProvider):
    """Hugging Face Inference API provider using huggingface_hub."""

    provider_name = "huggingface"

    def __init__(self, token: Optional[str] = None):
        try:
            from huggingface_hub import InferenceClient
        except ImportError:
            raise ImportError(
                "huggingface_hub package not installed. Install with: pip install huggingface_hub"
            )

        self._token = token or os.getenv("HF_TOKEN")
        if not self._token:
            raise ValueError("HF_TOKEN not set")

        self._client = InferenceClient(token=self._token)
        self._last_usage = {}

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        model = model or "meta-llama/Llama-3.1-70B-Instruct"
        if model.startswith("hf/"):
            model = model[len("hf/") :]

        response = self._client.chat_completion(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        usage = getattr(response, "usage", None)
        self._last_usage = {
            "input_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
            "output_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
        }
        return response.choices[0].message.content or ""

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> str:
        model = model or "llava-hf/llava-v1.6-mistral-7b-hf"
        if model.startswith("hf/"):
            model = model[len("hf/") :]

        b64 = base64.b64encode(image_bytes).decode()

        response = self._client.chat_completion(
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

        usage = getattr(response, "usage", None)
        self._last_usage = {
            "input_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
            "output_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
        }
        return response.choices[0].message.content or ""

    def transcribe_audio(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        model = model or "openai/whisper-large-v3"
        if model.startswith("hf/"):
            model = model[len("hf/") :]

        audio_path = Path(audio_path)
        audio_bytes = audio_path.read_bytes()

        result = self._client.automatic_speech_recognition(
            audio=audio_bytes,
            model=model,
        )

        text = result.text if hasattr(result, "text") else str(result)

        self._last_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
        }

        return {
            "text": text,
            "segments": [],
            "language": language,
            "duration": None,
            "provider": "huggingface",
            "model": model,
        }

    def list_models(self) -> list[ModelInfo]:
        return list(_HF_MODELS)


ProviderRegistry.register(
    name="huggingface",
    provider_class=HuggingFaceProvider,
    env_var="HF_TOKEN",
    model_prefixes=["hf/"],
    default_models={
        "chat": "meta-llama/Llama-3.1-70B-Instruct",
        "vision": "llava-hf/llava-v1.6-mistral-7b-hf",
        "audio": "openai/whisper-large-v3",
    },
)
