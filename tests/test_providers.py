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
        m = ModelInfo(
            id="claude-sonnet-4-5-20250929",
            provider="anthropic",
            display_name="Claude Sonnet",
            capabilities=["chat", "vision"],
        )
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
    @patch(
        "video_processor.providers.ollama_provider.OllamaProvider.is_available", return_value=False
    )
    @patch.dict("os.environ", {}, clear=True)
    def test_discover_skips_missing_keys(self, mock_ollama):
        from video_processor.providers.discovery import discover_available_models

        # No API keys and no Ollama -> empty list, no errors
        models = discover_available_models(api_keys={"openai": "", "anthropic": "", "gemini": ""})
        assert models == []

    @patch.dict("os.environ", {}, clear=True)
    @patch(
        "video_processor.providers.ollama_provider.OllamaProvider.is_available", return_value=False
    )
    @patch("video_processor.providers.discovery._cached_models", None)
    def test_discover_caches_results(self, mock_ollama):
        from video_processor.providers import discovery

        models = discovery.discover_available_models(
            api_keys={"openai": "", "anthropic": "", "gemini": ""}
        )
        assert models == []
        # Second call should use cache
        models2 = discovery.discover_available_models(api_keys={"openai": "key"})
        assert models2 == []  # Still cached empty result

        # Force refresh
        discovery.clear_discovery_cache()
        # Would try to connect with real key, so skip that test


class TestOllamaProvider:
    @patch("video_processor.providers.ollama_provider.requests")
    def test_is_available_when_running(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_requests.get.return_value = mock_resp

        from video_processor.providers.ollama_provider import OllamaProvider

        assert OllamaProvider.is_available()

    @patch("video_processor.providers.ollama_provider.requests")
    def test_is_available_when_not_running(self, mock_requests):
        mock_requests.get.side_effect = ConnectionError

        from video_processor.providers.ollama_provider import OllamaProvider

        assert not OllamaProvider.is_available()

    @patch("video_processor.providers.ollama_provider.requests")
    @patch("video_processor.providers.ollama_provider.OpenAI")
    def test_transcribe_raises(self, mock_openai, mock_requests):
        from video_processor.providers.ollama_provider import OllamaProvider

        provider = OllamaProvider()
        with pytest.raises(NotImplementedError):
            provider.transcribe_audio("/tmp/test.wav")

    @patch("video_processor.providers.ollama_provider.requests")
    @patch("video_processor.providers.ollama_provider.OpenAI")
    def test_list_models(self, mock_openai, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [
                {"name": "llama3.2:latest", "details": {"family": "llama"}},
                {"name": "llava:13b", "details": {"family": "llava"}},
            ]
        }
        mock_requests.get.return_value = mock_resp

        from video_processor.providers.ollama_provider import OllamaProvider

        provider = OllamaProvider()
        models = provider.list_models()
        assert len(models) == 2
        assert models[0].provider == "ollama"

        # llava should have vision capability
        llava = [m for m in models if "llava" in m.id][0]
        assert "vision" in llava.capabilities

        # llama should have only chat
        llama = [m for m in models if "llama" in m.id][0]
        assert "chat" in llama.capabilities
        assert "vision" not in llama.capabilities

    def test_provider_for_model_ollama_via_discovery(self):
        mgr = ProviderManager()
        mgr._available_models = [
            ModelInfo(id="llama3.2:latest", provider="ollama", capabilities=["chat"]),
        ]
        assert mgr._provider_for_model("llama3.2:latest") == "ollama"

    def test_provider_for_model_ollama_fuzzy_tag(self):
        mgr = ProviderManager()
        mgr._available_models = [
            ModelInfo(id="llama3.2:latest", provider="ollama", capabilities=["chat"]),
        ]
        # Should match "llama3.2" to "llama3.2:latest" via prefix
        assert mgr._provider_for_model("llama3.2") == "ollama"

    def test_init_forced_provider_ollama(self):
        mgr = ProviderManager(provider="ollama")
        # Ollama defaults are empty (resolved dynamically)
        assert mgr.vision_model == ""
        assert mgr.chat_model == ""
        assert mgr.transcription_model == ""
