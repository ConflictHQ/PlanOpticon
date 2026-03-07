"""Unified OAuth and authentication strategy for PlanOpticon connectors.

Provides a consistent auth pattern across all source connectors:
1. Saved token (auto-refresh if expired)
2. OAuth 2.0 (Authorization Code with PKCE, or Client Credentials)
3. API key fallback (environment variable)

Usage in a connector:

    from video_processor.auth import OAuthManager, AuthConfig

    config = AuthConfig(
        service="notion",
        oauth_authorize_url="https://api.notion.com/v1/oauth/authorize",
        oauth_token_url="https://api.notion.com/v1/oauth/token",
        client_id_env="NOTION_CLIENT_ID",
        client_secret_env="NOTION_CLIENT_SECRET",
        api_key_env="NOTION_API_KEY",
        scopes=["read_content"],
    )
    manager = OAuthManager(config)
    token = manager.authenticate()  # Returns access token or None
"""

import base64
import hashlib
import json
import logging
import os
import secrets
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

TOKEN_DIR = Path.home() / ".planopticon"


@dataclass
class AuthConfig:
    """Configuration for a service's authentication."""

    service: str

    # OAuth endpoints (set both for OAuth support)
    oauth_authorize_url: Optional[str] = None
    oauth_token_url: Optional[str] = None

    # Client credentials (checked from env if not provided)
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    client_id_env: Optional[str] = None
    client_secret_env: Optional[str] = None

    # API key fallback
    api_key_env: Optional[str] = None

    # OAuth scopes
    scopes: List[str] = field(default_factory=list)

    # Redirect URI for auth code flow
    redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob"

    # Server-to-Server (client credentials grant)
    account_id: Optional[str] = None
    account_id_env: Optional[str] = None

    # Token storage
    token_path: Optional[Path] = None

    @property
    def resolved_client_id(self) -> Optional[str]:
        return (
            self.client_id
            or (os.environ.get(self.client_id_env, "") if self.client_id_env else None)
            or None
        )

    @property
    def resolved_client_secret(self) -> Optional[str]:
        return (
            self.client_secret
            or (os.environ.get(self.client_secret_env, "") if self.client_secret_env else None)
            or None
        )

    @property
    def resolved_api_key(self) -> Optional[str]:
        if self.api_key_env:
            val = os.environ.get(self.api_key_env, "")
            return val if val else None
        return None

    @property
    def resolved_account_id(self) -> Optional[str]:
        return (
            self.account_id
            or (os.environ.get(self.account_id_env, "") if self.account_id_env else None)
            or None
        )

    @property
    def resolved_token_path(self) -> Path:
        return self.token_path or TOKEN_DIR / f"{self.service}_token.json"

    @property
    def supports_oauth(self) -> bool:
        return bool(self.oauth_authorize_url and self.oauth_token_url)


@dataclass
class AuthResult:
    """Result of an authentication attempt."""

    success: bool
    access_token: Optional[str] = None
    method: Optional[str] = None  # "saved_token", "oauth_pkce", "client_credentials", "api_key"
    expires_at: Optional[float] = None
    refresh_token: Optional[str] = None
    error: Optional[str] = None


class OAuthManager:
    """Manages OAuth and API key authentication for a service.

    Tries auth methods in order:
    1. Load saved token (refresh if expired)
    2. Client Credentials grant (if account_id is set)
    3. OAuth2 Authorization Code with PKCE (interactive)
    4. API key fallback
    """

    def __init__(self, config: AuthConfig):
        self.config = config
        self._token_data: Optional[Dict] = None

    def authenticate(self) -> AuthResult:
        """Run the auth chain and return the result."""
        # 1. Saved token
        result = self._try_saved_token()
        if result.success:
            return result

        # 2. Client Credentials (Server-to-Server)
        if self.config.resolved_account_id and self.config.supports_oauth:
            result = self._try_client_credentials()
            if result.success:
                return result

        # 3. OAuth PKCE (interactive)
        if self.config.supports_oauth and self.config.resolved_client_id:
            result = self._try_oauth_pkce()
            if result.success:
                return result

        # 4. API key fallback
        api_key = self.config.resolved_api_key
        if api_key:
            return AuthResult(
                success=True,
                access_token=api_key,
                method="api_key",
            )

        return AuthResult(
            success=False,
            error=f"No auth method available for {self.config.service}",
        )

    def get_token(self) -> Optional[str]:
        """Convenience: authenticate and return just the token."""
        result = self.authenticate()
        return result.access_token if result.success else None

    def _try_saved_token(self) -> AuthResult:
        """Load and validate a saved token."""
        token_path = self.config.resolved_token_path
        if not token_path.exists():
            return AuthResult(success=False)

        try:
            data = json.loads(token_path.read_text())
            expires_at = data.get("expires_at", 0)

            if time.time() < expires_at:
                self._token_data = data
                return AuthResult(
                    success=True,
                    access_token=data["access_token"],
                    method="saved_token",
                    expires_at=expires_at,
                )

            # Expired — try refresh
            if data.get("refresh_token"):
                return self._refresh_token(data)

            return AuthResult(success=False)
        except Exception as exc:
            logger.debug("Failed to load saved token for %s: %s", self.config.service, exc)
            return AuthResult(success=False)

    def _refresh_token(self, data: Dict) -> AuthResult:
        """Refresh an expired OAuth token."""
        try:
            import requests
        except ImportError:
            return AuthResult(success=False, error="requests not installed")

        client_id = data.get("client_id") or self.config.resolved_client_id
        client_secret = data.get("client_secret") or self.config.resolved_client_secret

        if not client_id or not data.get("refresh_token"):
            return AuthResult(success=False)

        try:
            resp = requests.post(
                self.config.oauth_token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": data["refresh_token"],
                },
                auth=(client_id, client_secret or ""),
                timeout=30,
            )
            resp.raise_for_status()
            token_data = resp.json()

            new_data = {
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token", data["refresh_token"]),
                "expires_at": time.time() + token_data.get("expires_in", 3600) - 60,
                "client_id": client_id,
                "client_secret": client_secret or "",
            }
            self._save_token(new_data)
            self._token_data = new_data

            logger.info("Refreshed OAuth token for %s", self.config.service)
            return AuthResult(
                success=True,
                access_token=new_data["access_token"],
                method="saved_token",
                expires_at=new_data["expires_at"],
                refresh_token=new_data["refresh_token"],
            )
        except Exception as exc:
            logger.debug("Token refresh failed for %s: %s", self.config.service, exc)
            return AuthResult(success=False)

    def _try_client_credentials(self) -> AuthResult:
        """Server-to-Server OAuth using client credentials grant."""
        try:
            import requests
        except ImportError:
            return AuthResult(success=False, error="requests not installed")

        client_id = self.config.resolved_client_id
        client_secret = self.config.resolved_client_secret
        account_id = self.config.resolved_account_id

        if not client_id or not client_secret:
            return AuthResult(success=False)

        try:
            resp = requests.post(
                self.config.oauth_token_url,
                params={
                    "grant_type": "account_credentials",
                    "account_id": account_id,
                },
                auth=(client_id, client_secret),
                timeout=30,
            )
            resp.raise_for_status()
            token_data = resp.json()

            data = {
                "access_token": token_data["access_token"],
                "expires_at": time.time() + token_data.get("expires_in", 3600) - 60,
            }
            self._save_token(data)
            self._token_data = data

            logger.info("Authenticated %s via client credentials", self.config.service)
            return AuthResult(
                success=True,
                access_token=data["access_token"],
                method="client_credentials",
                expires_at=data["expires_at"],
            )
        except Exception as exc:
            logger.debug("Client credentials failed for %s: %s", self.config.service, exc)
            return AuthResult(success=False)

    def _try_oauth_pkce(self) -> AuthResult:
        """Interactive OAuth2 Authorization Code flow with PKCE."""
        try:
            import requests
        except ImportError:
            return AuthResult(success=False, error="requests not installed")

        client_id = self.config.resolved_client_id
        if not client_id:
            return AuthResult(success=False)

        # Generate PKCE verifier and challenge
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )

        # Build authorize URL
        params = (
            f"?response_type=code"
            f"&client_id={client_id}"
            f"&redirect_uri={self.config.redirect_uri}"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )
        if self.config.scopes:
            params += f"&scope={'+'.join(self.config.scopes)}"

        authorize_url = f"{self.config.oauth_authorize_url}{params}"

        print(f"\nOpen this URL to authorize PlanOpticon ({self.config.service}):")
        print(f"{authorize_url}\n")

        try:
            webbrowser.open(authorize_url)
        except Exception:
            pass

        try:
            auth_code = input("Enter the authorization code: ").strip()
        except (KeyboardInterrupt, EOFError):
            return AuthResult(success=False, error="Auth cancelled by user")

        if not auth_code:
            return AuthResult(success=False, error="No auth code provided")

        # Exchange code for tokens
        client_secret = self.config.resolved_client_secret
        try:
            resp = requests.post(
                self.config.oauth_token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "redirect_uri": self.config.redirect_uri,
                    "code_verifier": code_verifier,
                },
                auth=(client_id, client_secret or ""),
                timeout=30,
            )
            resp.raise_for_status()
            token_data = resp.json()

            data = {
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": time.time() + token_data.get("expires_in", 3600) - 60,
                "client_id": client_id,
                "client_secret": client_secret or "",
            }
            self._save_token(data)
            self._token_data = data

            logger.info("Authenticated %s via OAuth PKCE", self.config.service)
            return AuthResult(
                success=True,
                access_token=data["access_token"],
                method="oauth_pkce",
                expires_at=data["expires_at"],
                refresh_token=data.get("refresh_token"),
            )
        except Exception as exc:
            logger.debug("OAuth PKCE failed for %s: %s", self.config.service, exc)
            return AuthResult(success=False, error=str(exc))

    def _save_token(self, data: Dict) -> None:
        """Persist token data to disk."""
        token_path = self.config.resolved_token_path
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(json.dumps(data))
        logger.info("Saved %s token to %s", self.config.service, token_path)

    def clear_token(self) -> None:
        """Remove saved token (logout)."""
        token_path = self.config.resolved_token_path
        if token_path.exists():
            token_path.unlink()
            logger.info("Cleared %s token", self.config.service)


# -----------------------------------------------------------------------
# Pre-built configs for known services
# -----------------------------------------------------------------------

KNOWN_CONFIGS: Dict[str, AuthConfig] = {
    "zoom": AuthConfig(
        service="zoom",
        oauth_authorize_url="https://zoom.us/oauth/authorize",
        oauth_token_url="https://zoom.us/oauth/token",
        client_id_env="ZOOM_CLIENT_ID",
        client_secret_env="ZOOM_CLIENT_SECRET",
        account_id_env="ZOOM_ACCOUNT_ID",
    ),
    "notion": AuthConfig(
        service="notion",
        oauth_authorize_url="https://api.notion.com/v1/oauth/authorize",
        oauth_token_url="https://api.notion.com/v1/oauth/token",
        client_id_env="NOTION_CLIENT_ID",
        client_secret_env="NOTION_CLIENT_SECRET",
        api_key_env="NOTION_API_KEY",
    ),
    "dropbox": AuthConfig(
        service="dropbox",
        oauth_authorize_url="https://www.dropbox.com/oauth2/authorize",
        oauth_token_url="https://api.dropboxapi.com/oauth2/token",
        client_id_env="DROPBOX_APP_KEY",
        client_secret_env="DROPBOX_APP_SECRET",
        api_key_env="DROPBOX_ACCESS_TOKEN",
    ),
    "github": AuthConfig(
        service="github",
        oauth_authorize_url="https://github.com/login/oauth/authorize",
        oauth_token_url="https://github.com/login/oauth/access_token",
        client_id_env="GITHUB_CLIENT_ID",
        client_secret_env="GITHUB_CLIENT_SECRET",
        api_key_env="GITHUB_TOKEN",
        scopes=["repo", "read:org"],
    ),
    "google": AuthConfig(
        service="google",
        oauth_authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        oauth_token_url="https://oauth2.googleapis.com/token",
        client_id_env="GOOGLE_CLIENT_ID",
        client_secret_env="GOOGLE_CLIENT_SECRET",
        api_key_env="GOOGLE_API_KEY",
        scopes=[
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/documents.readonly",
        ],
    ),
    "microsoft": AuthConfig(
        service="microsoft",
        oauth_authorize_url=("https://login.microsoftonline.com/common/oauth2/v2.0/authorize"),
        oauth_token_url=("https://login.microsoftonline.com/common/oauth2/v2.0/token"),
        client_id_env="MICROSOFT_CLIENT_ID",
        client_secret_env="MICROSOFT_CLIENT_SECRET",
        scopes=[
            "https://graph.microsoft.com/OnlineMeetings.Read",
            "https://graph.microsoft.com/Files.Read",
        ],
    ),
}


def get_auth_config(service: str) -> Optional[AuthConfig]:
    """Get a pre-built AuthConfig for a known service."""
    return KNOWN_CONFIGS.get(service)


def get_auth_manager(service: str) -> Optional[OAuthManager]:
    """Get an OAuthManager for a known service."""
    config = get_auth_config(service)
    if config:
        return OAuthManager(config)
    return None
