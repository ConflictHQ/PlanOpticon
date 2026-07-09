"""Branch coverage for OAuthManager grant flows (complements test_auth.py).

Covers the untested paths in video_processor.auth: client-credentials grant,
OAuth2 PKCE authorize-url construction + code exchange, refresh failure modes,
the authenticate() fallback chain ordering, and the missing-requests guards.
Mocks only true boundaries: requests.post, webbrowser.open, builtins.input.
Token files are written to real tmp_path files and read back.
"""

import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

from video_processor.auth import AuthConfig, OAuthManager


def _mock_resp(payload):
    """Build a fake requests.Response whose .json() returns *payload*."""
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


# -----------------------------------------------------------------------
# AuthConfig.resolved_client_secret (line 84)
# -----------------------------------------------------------------------


class TestResolvedClientSecret:
    def test_from_env(self):
        config = AuthConfig(service="test", client_secret_env="TEST_SECRET")
        with patch.dict(os.environ, {"TEST_SECRET": "shh"}, clear=True):
            assert config.resolved_client_secret == "shh"

    def test_explicit_wins(self):
        config = AuthConfig(
            service="test",
            client_secret="explicit-secret",
            client_secret_env="TEST_SECRET",
        )
        assert config.resolved_client_secret == "explicit-secret"

    def test_none_when_unset(self):
        config = AuthConfig(service="test", client_secret_env="TEST_SECRET")
        with patch.dict(os.environ, {}, clear=True):
            assert config.resolved_client_secret is None


# -----------------------------------------------------------------------
# Client Credentials grant (Server-to-Server)
# -----------------------------------------------------------------------


class TestClientCredentials:
    def _config(self, tmp_path):
        return AuthConfig(
            service="svc",
            oauth_authorize_url="https://svc.example/authorize",
            oauth_token_url="https://svc.example/token",
            client_id="cid",
            client_secret="csec",
            account_id="acct-1",
            token_path=tmp_path / "cc_token.json",
        )

    def test_success_via_authenticate(self, tmp_path):
        config = self._config(tmp_path)
        manager = OAuthManager(config)
        resp = _mock_resp({"access_token": "cc-tok", "expires_in": 3600})

        with patch("requests.post", return_value=resp) as mock_post:
            result = manager.authenticate()

        assert result.success
        assert result.method == "client_credentials"
        assert result.access_token == "cc-tok"
        # expires_at is now + expires_in - 60 (a minute of safety margin)
        assert result.expires_at > time.time()

        # Real token file was written and is readable.
        saved = json.loads((tmp_path / "cc_token.json").read_text())
        assert saved["access_token"] == "cc-tok"

        # Correct grant params + HTTP basic auth were sent.
        _, kwargs = mock_post.call_args
        assert kwargs["params"]["grant_type"] == "account_credentials"
        assert kwargs["params"]["account_id"] == "acct-1"
        assert kwargs["auth"] == ("cid", "csec")

    def test_missing_secret_returns_failure(self, tmp_path):
        config = AuthConfig(
            service="svc",
            oauth_authorize_url="https://svc.example/authorize",
            oauth_token_url="https://svc.example/token",
            client_id="cid",
            account_id="acct-1",
            token_path=tmp_path / "tok.json",
        )
        manager = OAuthManager(config)
        with patch.dict(os.environ, {}, clear=True):
            result = manager._try_client_credentials()
        assert not result.success

    def test_http_error_returns_failure(self, tmp_path):
        config = self._config(tmp_path)
        manager = OAuthManager(config)
        resp = MagicMock()
        resp.raise_for_status.side_effect = RuntimeError("boom 500")

        with patch("requests.post", return_value=resp):
            result = manager._try_client_credentials()

        assert not result.success
        assert not (tmp_path / "cc_token.json").exists()

    def test_requests_missing_returns_failure(self, tmp_path):
        config = self._config(tmp_path)
        manager = OAuthManager(config)
        with patch.dict(sys.modules, {"requests": None}):
            result = manager._try_client_credentials()
        assert not result.success
        assert result.error == "requests not installed"


# -----------------------------------------------------------------------
# OAuth2 Authorization Code + PKCE
# -----------------------------------------------------------------------


class TestOAuthPKCE:
    def _config(self, tmp_path, scopes=None):
        return AuthConfig(
            service="pk",
            oauth_authorize_url="https://pk.example/authorize",
            oauth_token_url="https://pk.example/token",
            client_id="pk-client",
            client_secret="pk-secret",
            scopes=scopes if scopes is not None else ["read", "write"],
            token_path=tmp_path / "pk_token.json",
        )

    def test_success_via_authenticate(self, tmp_path):
        config = self._config(tmp_path)
        manager = OAuthManager(config)
        resp = _mock_resp({"access_token": "pk-tok", "refresh_token": "pk-ref", "expires_in": 3600})

        with (
            patch("webbrowser.open") as mock_open,
            patch("builtins.input", return_value="the-auth-code"),
            patch("requests.post", return_value=resp) as mock_post,
        ):
            result = manager.authenticate()

        assert result.success
        assert result.method == "oauth_pkce"
        assert result.access_token == "pk-tok"
        assert result.refresh_token == "pk-ref"

        # The authorize URL opened in the browser is a well-formed PKCE request.
        authorize_url = mock_open.call_args[0][0]
        assert authorize_url.startswith("https://pk.example/authorize?")
        assert "response_type=code" in authorize_url
        assert "client_id=pk-client" in authorize_url
        assert "code_challenge=" in authorize_url
        assert "code_challenge_method=S256" in authorize_url
        assert "scope=read+write" in authorize_url

        # The code exchange sent the verifier and the user's code.
        _, kwargs = mock_post.call_args
        assert kwargs["data"]["grant_type"] == "authorization_code"
        assert kwargs["data"]["code"] == "the-auth-code"
        assert kwargs["data"]["code_verifier"]
        assert kwargs["auth"] == ("pk-client", "pk-secret")

        # Token persisted to a real file with the client identity recorded.
        saved = json.loads((tmp_path / "pk_token.json").read_text())
        assert saved["access_token"] == "pk-tok"
        assert saved["client_id"] == "pk-client"

    def test_no_scopes_omits_scope_param(self, tmp_path):
        config = self._config(tmp_path, scopes=[])
        manager = OAuthManager(config)
        resp = _mock_resp({"access_token": "pk-tok", "expires_in": 3600})

        with (
            patch("webbrowser.open") as mock_open,
            patch("builtins.input", return_value="code"),
            patch("requests.post", return_value=resp),
        ):
            result = manager.authenticate()

        assert result.success
        assert "scope=" not in mock_open.call_args[0][0]

    def test_webbrowser_failure_still_proceeds(self, tmp_path):
        config = self._config(tmp_path)
        manager = OAuthManager(config)
        resp = _mock_resp({"access_token": "pk-tok", "expires_in": 3600})

        with (
            patch("webbrowser.open", side_effect=RuntimeError("no display")),
            patch("builtins.input", return_value="code"),
            patch("requests.post", return_value=resp),
        ):
            result = manager._try_oauth_pkce()

        assert result.success
        assert result.access_token == "pk-tok"

    def test_no_client_id_returns_failure(self, tmp_path):
        config = AuthConfig(
            service="pk",
            oauth_authorize_url="https://pk.example/authorize",
            oauth_token_url="https://pk.example/token",
            token_path=tmp_path / "tok.json",
        )
        manager = OAuthManager(config)
        with patch.dict(os.environ, {}, clear=True):
            result = manager._try_oauth_pkce()
        assert not result.success

    def test_empty_code_returns_error(self, tmp_path):
        config = self._config(tmp_path)
        manager = OAuthManager(config)
        with (
            patch("webbrowser.open"),
            patch("builtins.input", return_value="   "),
        ):
            result = manager._try_oauth_pkce()
        assert not result.success
        assert result.error == "No auth code provided"

    def test_cancelled_by_user(self, tmp_path):
        config = self._config(tmp_path)
        manager = OAuthManager(config)
        with (
            patch("webbrowser.open"),
            patch("builtins.input", side_effect=KeyboardInterrupt),
        ):
            result = manager._try_oauth_pkce()
        assert not result.success
        assert result.error == "Auth cancelled by user"

    def test_code_exchange_error(self, tmp_path):
        config = self._config(tmp_path)
        manager = OAuthManager(config)
        resp = MagicMock()
        resp.raise_for_status.side_effect = RuntimeError("bad code")

        with (
            patch("webbrowser.open"),
            patch("builtins.input", return_value="code"),
            patch("requests.post", return_value=resp),
        ):
            result = manager._try_oauth_pkce()

        assert not result.success
        assert result.error is not None
        assert not (tmp_path / "pk_token.json").exists()

    def test_requests_missing_returns_failure(self, tmp_path):
        config = self._config(tmp_path)
        manager = OAuthManager(config)
        with patch.dict(sys.modules, {"requests": None}):
            result = manager._try_oauth_pkce()
        assert not result.success
        assert result.error == "requests not installed"


# -----------------------------------------------------------------------
# Refresh-token failure modes (test_auth.py covers the success path)
# -----------------------------------------------------------------------


class TestRefreshFailures:
    def test_no_refresh_token_reused_from_response(self, tmp_path):
        """When the refresh response omits refresh_token, the old one is kept."""
        token_file = tmp_path / "token.json"
        token_file.write_text(
            json.dumps(
                {
                    "access_token": "old",
                    "refresh_token": "keep-me",
                    "expires_at": time.time() - 100,
                    "client_id": "cid",
                    "client_secret": "csec",
                }
            )
        )
        config = AuthConfig(
            service="svc",
            oauth_token_url="https://svc.example/token",
            token_path=token_file,
        )
        manager = OAuthManager(config)
        resp = _mock_resp({"access_token": "fresh", "expires_in": 3600})

        with patch("requests.post", return_value=resp):
            result = manager.authenticate()

        assert result.success
        assert result.access_token == "fresh"
        # Old refresh token carried forward and persisted.
        assert result.refresh_token == "keep-me"
        assert json.loads(token_file.read_text())["refresh_token"] == "keep-me"

    def test_missing_client_id_aborts_refresh(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text(
            json.dumps(
                {
                    "access_token": "old",
                    "refresh_token": "ref",
                    "expires_at": time.time() - 100,
                }
            )
        )
        config = AuthConfig(
            service="svc",
            oauth_token_url="https://svc.example/token",
            token_path=token_file,
        )
        manager = OAuthManager(config)
        with patch.dict(os.environ, {}, clear=True):
            result = manager.authenticate()
        assert not result.success

    def test_network_error_during_refresh(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text(
            json.dumps(
                {
                    "access_token": "old",
                    "refresh_token": "ref",
                    "expires_at": time.time() - 100,
                    "client_id": "cid",
                    "client_secret": "csec",
                }
            )
        )
        config = AuthConfig(
            service="svc",
            oauth_token_url="https://svc.example/token",
            token_path=token_file,
        )
        manager = OAuthManager(config)
        with patch("requests.post", side_effect=RuntimeError("network down")):
            result = manager.authenticate()
        assert not result.success

    def test_requests_missing_during_refresh(self, tmp_path):
        data = {
            "access_token": "old",
            "refresh_token": "ref",
            "expires_at": time.time() - 100,
            "client_id": "cid",
        }
        config = AuthConfig(
            service="svc",
            oauth_token_url="https://svc.example/token",
            token_path=tmp_path / "token.json",
        )
        manager = OAuthManager(config)
        with patch.dict(sys.modules, {"requests": None}):
            result = manager._refresh_token(data)
        assert not result.success
        assert result.error == "requests not installed"


# -----------------------------------------------------------------------
# Saved-token load failure + authenticate() chain ordering + error hints
# -----------------------------------------------------------------------


class TestAuthenticateChain:
    def test_corrupt_saved_token_falls_through(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text("this is not valid json {{{")
        config = AuthConfig(
            service="svc",
            api_key_env="SVC_KEY",
            token_path=token_file,
        )
        manager = OAuthManager(config)
        with patch.dict(os.environ, {"SVC_KEY": "sk-fallback"}):
            result = manager.authenticate()
        # Corrupt token is ignored; the chain continues to the API key fallback.
        assert result.success
        assert result.method == "api_key"
        assert result.access_token == "sk-fallback"

    def test_client_credentials_preferred_over_pkce(self, tmp_path):
        """account_id present -> client-credentials grant is tried before PKCE."""
        config = AuthConfig(
            service="svc",
            oauth_authorize_url="https://svc.example/authorize",
            oauth_token_url="https://svc.example/token",
            client_id="cid",
            client_secret="csec",
            account_id="acct",
            token_path=tmp_path / "token.json",
        )
        manager = OAuthManager(config)
        resp = _mock_resp({"access_token": "cc", "expires_in": 3600})

        # input is NOT patched: if PKCE were reached it would try to read stdin.
        with patch("requests.post", return_value=resp):
            result = manager.authenticate()

        assert result.success
        assert result.method == "client_credentials"

    def test_error_message_lists_all_hints(self, tmp_path):
        config = AuthConfig(
            service="svc",
            oauth_authorize_url="https://svc.example/authorize",
            oauth_token_url="https://svc.example/token",
            client_id_env="SVC_CID",
            client_secret_env="SVC_SEC",
            api_key_env="SVC_KEY",
            token_path=tmp_path / "nope.json",
        )
        manager = OAuthManager(config)
        with patch.dict(os.environ, {}, clear=True):
            result = manager.authenticate()

        assert not result.success
        assert "SVC_CID" in result.error
        assert "SVC_SEC" in result.error
        assert "SVC_KEY" in result.error
        assert "OAuth" in result.error
