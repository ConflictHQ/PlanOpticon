"""Tests for AnthropicProvider (chat, vision, transcription guard, listing).

Mocks only the anthropic SDK client so the real request/response mapping runs.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from video_processor.providers.anthropic_provider import AnthropicProvider


def _provider():
    """Build a provider with a fake key and a mock client attached."""
    with patch("anthropic.Anthropic") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        provider = AnthropicProvider(api_key="sk-ant-test")
    provider.client = client
    return provider, client


def _message_response(text, input_tokens=8, output_tokens=16):
    resp = MagicMock()
    block = MagicMock()
    block.text = text
    resp.content = [block]
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens
    return resp


class TestConstruction:
    def test_missing_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not set"):
                AnthropicProvider(api_key=None)

    @patch("anthropic.Anthropic")
    def test_builds_client_with_key(self, mock_cls):
        client = MagicMock()
        mock_cls.return_value = client
        provider = AnthropicProvider(api_key="sk-ant-test")
        assert provider.client is client
        mock_cls.assert_called_once_with(api_key="sk-ant-test")


class TestChat:
    def test_chat_returns_text_and_usage(self):
        provider, client = _provider()
        client.messages.create.return_value = _message_response("hi there", 8, 20)

        out = provider.chat([{"role": "user", "content": "hi"}])
        assert out == "hi there"
        assert provider._last_usage == {"input_tokens": 8, "output_tokens": 20}
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-haiku-4-5-20251001"  # default
        assert "system" not in kwargs  # no system message supplied

    def test_chat_hoists_system_messages_to_top_level(self):
        provider, client = _provider()
        client.messages.create.return_value = _message_response("ok")

        provider.chat(
            [
                {"role": "system", "content": "Be terse."},
                {"role": "system", "content": "Answer in English."},
                {"role": "user", "content": "hi"},
            ],
            model="claude-sonnet-4-5-20250929",
        )
        kwargs = client.messages.create.call_args.kwargs
        # system parts are joined and lifted out of the messages list
        assert kwargs["system"] == "Be terse.\n\nAnswer in English."
        assert kwargs["messages"] == [{"role": "user", "content": "hi"}]
        assert kwargs["model"] == "claude-sonnet-4-5-20250929"


class TestAnalyzeImage:
    def test_analyze_image_builds_base64_block(self):
        provider, client = _provider()
        client.messages.create.return_value = _message_response("a diagram", 120, 4)

        out = provider.analyze_image(b"\x89PNGdata", "describe")
        assert out == "a diagram"
        assert provider._last_usage["input_tokens"] == 120

        content = client.messages.create.call_args.kwargs["messages"][0]["content"]
        image_block = [b for b in content if b["type"] == "image"][0]
        assert image_block["source"]["type"] == "base64"
        assert image_block["source"]["media_type"] == "image/jpeg"
        assert image_block["source"]["data"]  # non-empty base64 payload
        text_block = [b for b in content if b["type"] == "text"][0]
        assert text_block["text"] == "describe"


class TestTranscribe:
    def test_transcribe_not_supported(self):
        provider, _ = _provider()
        with pytest.raises(NotImplementedError, match="does not provide"):
            provider.transcribe_audio("/tmp/audio.wav")


class TestListModels:
    def _model(self, mid, display=None):
        m = MagicMock()
        m.id = mid
        m.display_name = display or mid
        return m

    def test_list_models_all_have_chat_and_vision(self):
        provider, client = _provider()
        page = MagicMock()
        page.data = [
            self._model("claude-sonnet-4-5-20250929", "Claude Sonnet 4.5"),
            self._model("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
        ]
        client.models.list.return_value = page

        models = provider.list_models()
        assert len(models) == 2
        for m in models:
            assert m.provider == "anthropic"
            assert m.capabilities == ["chat", "vision"]
        # sorted by id
        assert [m.id for m in models] == sorted(m.id for m in models)
        client.models.list.assert_called_once_with(limit=100)

    def test_list_models_handles_error(self):
        provider, client = _provider()
        client.models.list.side_effect = RuntimeError("network down")
        assert provider.list_models() == []
