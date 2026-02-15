"""Tests for the provider abstraction layer."""

from unittest.mock import MagicMock, patch

import pytest

from video_processor.providers.base import BaseProvider, ModelInfo
from video_processor.providers.manager import ProviderManager


class TestModelInfo:
    def test_basic(self):
        m = ModelInfo(id="gpt-4o", provider="openai", capabilities=["chat", "vision"])
        assert m.id == "gpt-4o"
        assert "vision" in m.capabilities

    def test_round_trip(self):
        m = ModelInfo(id="claude-sonnet-4-5-20250929", provider="anthropic", display_name="Claude Sonnet", capabilities=["chat", "vision"])
        restored = ModelInfo.model_validate_json(m.model_dump_json())
        assert restored == m


class TestProviderManager:
    def _make_mock_provider(self, name="openai"):
        """Create a mock provider."""
        provider = MagicMock(spec=BaseProvider)
        provider.provider_name = name
        provider.chat.return_value = "test response"
        provider.analyze_image.return_value = "image analysis"
        provider.transcribe_audio.return_value = {
            "text": "hello world",
            "segments": [],
            "provider": name,
            "model": "test",
        }
        return provider

    def test_init_with_explicit_models(self):
        mgr = ProviderManager(
            vision_model="gpt-4o",
            chat_model="claude-sonnet-4-5-20250929",
            transcription_model="whisper-1",
        )
        assert mgr.vision_model == "gpt-4o"
        assert mgr.chat_model == "claude-sonnet-4-5-20250929"
        assert mgr.transcription_model == "whisper-1"

    def test_init_forced_provider(self):
        mgr = ProviderManager(provider="gemini")
        assert mgr.vision_model == "gemini-2.5-flash"
        assert mgr.chat_model == "gemini-2.5-flash"
        assert mgr.transcription_model == "gemini-2.5-flash"

    def test_provider_for_model(self):
        mgr = ProviderManager()
        assert mgr._provider_for_model("gpt-4o") == "openai"
        assert mgr._provider_for_model("claude-sonnet-4-5-20250929") == "anthropic"
        assert mgr._provider_for_model("gemini-2.5-flash") == "gemini"
        assert mgr._provider_for_model("whisper-1") == "openai"

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_chat_routes_to_provider(self):
        mgr = ProviderManager(chat_model="gpt-4o")
        mock_prov = self._make_mock_provider("openai")
        mgr._providers["openai"] = mock_prov

        result = mgr.chat([{"role": "user", "content": "hello"}])
        assert result == "test response"
        mock_prov.chat.assert_called_once()

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_analyze_image_routes(self):
        mgr = ProviderManager(vision_model="gpt-4o")
        mock_prov = self._make_mock_provider("openai")
        mgr._providers["openai"] = mock_prov

        result = mgr.analyze_image(b"fake-image", "describe this")
        assert result == "image analysis"
        mock_prov.analyze_image.assert_called_once()

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_transcribe_routes(self):
        mgr = ProviderManager(transcription_model="whisper-1")
        mock_prov = self._make_mock_provider("openai")
        mgr._providers["openai"] = mock_prov

        result = mgr.transcribe_audio("/tmp/test.wav")
        assert result["text"] == "hello world"
        mock_prov.transcribe_audio.assert_called_once()

    def test_get_models_used(self):
        mgr = ProviderManager(
            vision_model="gpt-4o",
            chat_model="claude-sonnet-4-5-20250929",
            transcription_model="whisper-1",
        )
        # Pre-fill providers so _resolve_model doesn't try to instantiate real ones
        for name in ["openai", "anthropic"]:
            mgr._providers[name] = self._make_mock_provider(name)

        used = mgr.get_models_used()
        assert "vision" in used
        assert "openai/gpt-4o" == used["vision"]
        assert "anthropic/claude-sonnet-4-5-20250929" == used["chat"]


class TestDiscovery:
    @patch("video_processor.providers.discovery._cached_models", None)
    @patch.dict("os.environ", {}, clear=True)
    def test_discover_skips_missing_keys(self):
        from video_processor.providers.discovery import discover_available_models
        # No API keys -> empty list, no errors
        models = discover_available_models(api_keys={"openai": "", "anthropic": "", "gemini": ""})
        assert models == []

    @patch.dict("os.environ", {}, clear=True)
    @patch("video_processor.providers.discovery._cached_models", None)
    def test_discover_caches_results(self):
        from video_processor.providers import discovery

        models = discovery.discover_available_models(api_keys={"openai": "", "anthropic": "", "gemini": ""})
        assert models == []
        # Second call should use cache
        models2 = discovery.discover_available_models(api_keys={"openai": "key"})
        assert models2 == []  # Still cached empty result

        # Force refresh
        discovery.clear_discovery_cache()
        # Would try to connect with real key, so skip that test
