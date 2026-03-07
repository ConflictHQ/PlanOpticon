"""Tests for the unified auth module."""

import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from video_processor.auth import (
    KNOWN_CONFIGS,
    AuthConfig,
    AuthResult,
    OAuthManager,
    get_auth_config,
    get_auth_manager,
)

# -----------------------------------------------------------------------
# AuthConfig
# -----------------------------------------------------------------------


class TestAuthConfig:
    def test_basic_creation(self):
        config = AuthConfig(service="test")
        assert config.service == "test"
        assert config.supports_oauth is False

    def test_with_oauth_endpoints(self):
        config = AuthConfig(
            service="test",
            oauth_authorize_url="https://example.com/auth",
            oauth_token_url="https://example.com/token",
        )
        assert config.supports_oauth is True

    def test_resolved_client_id_from_env(self):
        config = AuthConfig(
            service="test",
            client_id_env="TEST_CLIENT_ID",
        )
        with patch.dict(os.environ, {"TEST_CLIENT_ID": "my-id"}):
            assert config.resolved_client_id == "my-id"

    def test_resolved_client_id_explicit(self):
        config = AuthConfig(
            service="test",
            client_id="explicit-id",
            client_id_env="TEST_CLIENT_ID",
        )
        assert config.resolved_client_id == "explicit-id"

    def test_resolved_api_key(self):
        config = AuthConfig(service="test", api_key_env="TEST_API_KEY")
        with patch.dict(os.environ, {"TEST_API_KEY": "sk-123"}):
            assert config.resolved_api_key == "sk-123"

    def test_resolved_api_key_empty(self):
        config = AuthConfig(service="test", api_key_env="TEST_API_KEY")
        with patch.dict(os.environ, {}, clear=True):
            assert config.resolved_api_key is None

    def test_resolved_token_path_default(self):
        config = AuthConfig(service="zoom")
        assert config.resolved_token_path.name == "zoom_token.json"

    def test_resolved_token_path_custom(self):
        config = AuthConfig(
            service="zoom",
            token_path=Path("/tmp/custom.json"),
        )
        assert config.resolved_token_path == Path("/tmp/custom.json")

    def test_resolved_account_id(self):
        config = AuthConfig(
            service="test",
            account_id_env="TEST_ACCOUNT_ID",
        )
        with patch.dict(os.environ, {"TEST_ACCOUNT_ID": "acc-123"}):
            assert config.resolved_account_id == "acc-123"


# -----------------------------------------------------------------------
# AuthResult
# -----------------------------------------------------------------------


class TestAuthResult:
    def test_success(self):
        result = AuthResult(
            success=True,
            access_token="tok",
            method="api_key",
        )
        assert result.success
        assert result.access_token == "tok"

    def test_failure(self):
        result = AuthResult(success=False, error="no key")
        assert not result.success
        assert result.error == "no key"


# -----------------------------------------------------------------------
# OAuthManager
# -----------------------------------------------------------------------


class TestOAuthManager:
    def test_api_key_fallback(self):
        config = AuthConfig(
            service="test",
            api_key_env="TEST_KEY",
        )
        manager = OAuthManager(config)
        with patch.dict(os.environ, {"TEST_KEY": "sk-abc"}):
            result = manager.authenticate()
        assert result.success
        assert result.access_token == "sk-abc"
        assert result.method == "api_key"

    def test_no_auth_available(self):
        config = AuthConfig(service="test")
        manager = OAuthManager(config)
        with patch.dict(os.environ, {}, clear=True):
            result = manager.authenticate()
        assert not result.success
        assert "No auth method" in result.error

    def test_saved_token_valid(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_data = {
            "access_token": "saved-tok",
            "expires_at": time.time() + 3600,
        }
        token_file.write_text(json.dumps(token_data))

        config = AuthConfig(
            service="test",
            token_path=token_file,
        )
        manager = OAuthManager(config)
        result = manager.authenticate()
        assert result.success
        assert result.access_token == "saved-tok"
        assert result.method == "saved_token"

    def test_saved_token_expired_no_refresh(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_data = {
            "access_token": "old-tok",
            "expires_at": time.time() - 100,
        }
        token_file.write_text(json.dumps(token_data))

        config = AuthConfig(
            service="test",
            token_path=token_file,
        )
        manager = OAuthManager(config)
        result = manager.authenticate()
        assert not result.success

    def test_get_token_convenience(self):
        config = AuthConfig(
            service="test",
            api_key_env="TEST_KEY",
        )
        manager = OAuthManager(config)
        with patch.dict(os.environ, {"TEST_KEY": "sk-xyz"}):
            token = manager.get_token()
        assert token == "sk-xyz"

    def test_get_token_none_on_failure(self):
        config = AuthConfig(service="test")
        manager = OAuthManager(config)
        with patch.dict(os.environ, {}, clear=True):
            token = manager.get_token()
        assert token is None

    def test_clear_token(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text("{}")
        config = AuthConfig(service="test", token_path=token_file)
        manager = OAuthManager(config)
        manager.clear_token()
        assert not token_file.exists()

    def test_clear_token_no_file(self, tmp_path):
        config = AuthConfig(
            service="test",
            token_path=tmp_path / "nonexistent.json",
        )
        manager = OAuthManager(config)
        manager.clear_token()  # should not raise

    def test_save_token_creates_dir(self, tmp_path):
        nested = tmp_path / "deep" / "dir" / "token.json"
        config = AuthConfig(service="test", token_path=nested)
        manager = OAuthManager(config)
        manager._save_token({"access_token": "tok"})
        assert nested.exists()
        data = json.loads(nested.read_text())
        assert data["access_token"] == "tok"

    def test_saved_token_expired_with_refresh(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_data = {
            "access_token": "old-tok",
            "refresh_token": "ref-tok",
            "expires_at": time.time() - 100,
            "client_id": "cid",
            "client_secret": "csec",
        }
        token_file.write_text(json.dumps(token_data))

        config = AuthConfig(
            service="test",
            oauth_token_url="https://example.com/token",
            token_path=token_file,
        )
        manager = OAuthManager(config)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "new-tok",
            "refresh_token": "new-ref",
            "expires_in": 7200,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_resp):
            result = manager.authenticate()

        assert result.success
        assert result.access_token == "new-tok"
        assert result.method == "saved_token"

    def test_oauth_prefers_saved_over_api_key(self, tmp_path):
        """Saved token should be tried before API key fallback."""
        token_file = tmp_path / "token.json"
        token_data = {
            "access_token": "saved-tok",
            "expires_at": time.time() + 3600,
        }
        token_file.write_text(json.dumps(token_data))

        config = AuthConfig(
            service="test",
            api_key_env="TEST_KEY",
            token_path=token_file,
        )
        manager = OAuthManager(config)
        with patch.dict(os.environ, {"TEST_KEY": "api-key"}):
            result = manager.authenticate()

        assert result.access_token == "saved-tok"
        assert result.method == "saved_token"


# -----------------------------------------------------------------------
# Known configs and helpers
# -----------------------------------------------------------------------


class TestKnownConfigs:
    def test_zoom_config(self):
        config = KNOWN_CONFIGS["zoom"]
        assert config.service == "zoom"
        assert config.supports_oauth
        assert config.client_id_env == "ZOOM_CLIENT_ID"

    def test_notion_config(self):
        config = KNOWN_CONFIGS["notion"]
        assert config.api_key_env == "NOTION_API_KEY"
        assert config.supports_oauth

    def test_github_config(self):
        config = KNOWN_CONFIGS["github"]
        assert config.api_key_env == "GITHUB_TOKEN"
        assert "repo" in config.scopes

    def test_dropbox_config(self):
        config = KNOWN_CONFIGS["dropbox"]
        assert config.api_key_env == "DROPBOX_ACCESS_TOKEN"

    def test_google_config(self):
        config = KNOWN_CONFIGS["google"]
        assert config.supports_oauth

    def test_microsoft_config(self):
        config = KNOWN_CONFIGS["microsoft"]
        assert config.supports_oauth

    def test_all_configs_have_service(self):
        for name, config in KNOWN_CONFIGS.items():
            assert config.service == name

    def test_get_auth_config(self):
        assert get_auth_config("zoom") is not None
        assert get_auth_config("nonexistent") is None

    def test_get_auth_manager(self):
        mgr = get_auth_manager("zoom")
        assert mgr is not None
        assert isinstance(mgr, OAuthManager)

    def test_get_auth_manager_unknown(self):
        assert get_auth_manager("nonexistent") is None
