"""LiteLLM universal proxy provider implementation."""

import base64
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from video_processor.providers.base import BaseProvider, ModelInfo, ProviderRegistry

load_dotenv()
logger = logging.getLogger(__name__)


class LiteLLMProvider(BaseProvider):
    """LiteLLM universal proxy provider.

    LiteLLM supports 100+ LLM providers through a unified interface.
    It reads provider API keys from environment variables automatically
    (e.g. OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.).
    """

    provider_name = "litellm"

    def __init__(self):
        try:
            import litellm  # noqa: F401
        except ImportError:
            raise ImportError("litellm package not installed. Install with: pip install litellm")

        self._litellm = litellm
        self._last_usage = {}

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        if not model:
            raise ValueError(
                "LiteLLM requires an explicit model in provider/model format "
                "(e.g. 'openai/gpt-4o', 'anthropic/claude-3-sonnet-20240229')"
            )

        response = self._litellm.completion(
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
        if not model:
            raise ValueError(
                "LiteLLM requires an explicit model for image analysis "
                "(e.g. 'openai/gpt-4o', 'anthropic/claude-3-sonnet-20240229')"
            )

        b64 = base64.b64encode(image_bytes).decode()

        response = self._litellm.completion(
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
        model = model or "whisper-1"

        try:
            with open(audio_path, "rb") as f:
                response = self._litellm.transcription(
                    model=model,
                    file=f,
                    language=language,
                )

            text = getattr(response, "text", str(response))
            self._last_usage = {
                "input_tokens": 0,
                "output_tokens": 0,
            }

            return {
                "text": text,
                "segments": [],
                "language": language,
                "duration": None,
                "provider": "litellm",
                "model": model,
            }
        except Exception:
            raise NotImplementedError(
                "Audio transcription failed via LiteLLM. "
                "Ensure the underlying provider supports transcription."
            )

    def list_models(self) -> list[ModelInfo]:
        try:
            model_list = getattr(self._litellm, "model_list", None)
            if model_list:
                return [
                    ModelInfo(
                        id=m if isinstance(m, str) else str(m),
                        provider="litellm",
                        display_name=m if isinstance(m, str) else str(m),
                        capabilities=["chat"],
                    )
                    for m in model_list
                ]
        except Exception as e:
            logger.warning(f"Failed to list LiteLLM models: {e}")
        return []


# Only register if litellm is importable
try:
    import litellm  # noqa: F401

    ProviderRegistry.register(
        name="litellm",
        provider_class=LiteLLMProvider,
        env_var="",
        model_prefixes=[],
        default_models={
            "chat": "",
            "vision": "",
            "audio": "",
        },
    )
except ImportError:
    pass
