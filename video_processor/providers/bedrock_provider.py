"""AWS Bedrock provider implementation."""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from video_processor.providers.base import BaseProvider, ModelInfo, ProviderRegistry

load_dotenv()
logger = logging.getLogger(__name__)

# Curated list of popular Bedrock models
_BEDROCK_MODELS = [
    ModelInfo(
        id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        provider="bedrock",
        display_name="Claude 3.5 Sonnet v2",
        capabilities=["chat", "vision"],
    ),
    ModelInfo(
        id="anthropic.claude-3-sonnet-20240229-v1:0",
        provider="bedrock",
        display_name="Claude 3 Sonnet",
        capabilities=["chat", "vision"],
    ),
    ModelInfo(
        id="anthropic.claude-3-haiku-20240307-v1:0",
        provider="bedrock",
        display_name="Claude 3 Haiku",
        capabilities=["chat", "vision"],
    ),
    ModelInfo(
        id="amazon.titan-text-express-v1",
        provider="bedrock",
        display_name="Amazon Titan Text Express",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="meta.llama3-70b-instruct-v1:0",
        provider="bedrock",
        display_name="Llama 3 70B Instruct",
        capabilities=["chat"],
    ),
    ModelInfo(
        id="mistral.mistral-large-2402-v1:0",
        provider="bedrock",
        display_name="Mistral Large",
        capabilities=["chat"],
    ),
]


class BedrockProvider(BaseProvider):
    """AWS Bedrock provider using boto3."""

    provider_name = "bedrock"

    def __init__(
        self,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        region_name: Optional[str] = None,
    ):
        try:
            import boto3
        except ImportError:
            raise ImportError("boto3 package not installed. Install with: pip install boto3")

        self._boto3 = boto3
        self._region = region_name or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self._client = boto3.client(
            "bedrock-runtime",
            aws_access_key_id=aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=aws_secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=self._region,
        )
        self._last_usage = {}

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        model = model or "anthropic.claude-3-sonnet-20240229-v1:0"
        # Strip bedrock/ prefix if present
        if model.startswith("bedrock/"):
            model = model[len("bedrock/") :]

        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
            }
        )

        response = self._client.invoke_model(
            modelId=model,
            contentType="application/json",
            accept="application/json",
            body=body,
        )

        result = json.loads(response["body"].read())
        self._last_usage = {
            "input_tokens": result.get("usage", {}).get("input_tokens", 0),
            "output_tokens": result.get("usage", {}).get("output_tokens", 0),
        }
        return result.get("content", [{}])[0].get("text", "")

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> str:
        model = model or "anthropic.claude-3-sonnet-20240229-v1:0"
        if model.startswith("bedrock/"):
            model = model[len("bedrock/") :]

        b64 = base64.b64encode(image_bytes).decode()
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "messages": [
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
            }
        )

        response = self._client.invoke_model(
            modelId=model,
            contentType="application/json",
            accept="application/json",
            body=body,
        )

        result = json.loads(response["body"].read())
        self._last_usage = {
            "input_tokens": result.get("usage", {}).get("input_tokens", 0),
            "output_tokens": result.get("usage", {}).get("output_tokens", 0),
        }
        return result.get("content", [{}])[0].get("text", "")

    def transcribe_audio(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        raise NotImplementedError(
            "AWS Bedrock does not support audio transcription directly. "
            "Use Amazon Transcribe or another provider for transcription."
        )

    def list_models(self) -> list[ModelInfo]:
        return list(_BEDROCK_MODELS)


ProviderRegistry.register(
    name="bedrock",
    provider_class=BedrockProvider,
    env_var="AWS_ACCESS_KEY_ID",
    model_prefixes=["bedrock/"],
    default_models={
        "chat": "anthropic.claude-3-sonnet-20240229-v1:0",
        "vision": "anthropic.claude-3-sonnet-20240229-v1:0",
        "audio": "",
    },
)
