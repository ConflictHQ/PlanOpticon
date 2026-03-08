# Auth API Reference

::: video_processor.auth

---

## Overview

The `video_processor.auth` module provides a unified OAuth and authentication strategy for all PlanOpticon source connectors. It supports multiple authentication methods tried in a consistent order:

1. **Saved token** -- load from disk, auto-refresh if expired
2. **Client Credentials** -- server-to-server OAuth (e.g., Zoom S2S)
3. **OAuth 2.0 PKCE** -- interactive Authorization Code flow with PKCE
4. **API key fallback** -- environment variable lookup

Tokens are persisted to `~/.planopticon/` and automatically refreshed on expiry.

---

## AuthConfig

```python
from video_processor.auth import AuthConfig
```

Dataclass configuring authentication for a specific service. Defines OAuth endpoints, client credentials, API key fallback, scopes, and token storage.

### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `service` | `str` | *required* | Service identifier (e.g., `"zoom"`, `"notion"`) |
| `oauth_authorize_url` | `Optional[str]` | `None` | OAuth authorization endpoint URL |
| `oauth_token_url` | `Optional[str]` | `None` | OAuth token exchange endpoint URL |
| `client_id` | `Optional[str]` | `None` | OAuth client ID (direct value) |
| `client_secret` | `Optional[str]` | `None` | OAuth client secret (direct value) |
| `client_id_env` | `Optional[str]` | `None` | Environment variable for client ID |
| `client_secret_env` | `Optional[str]` | `None` | Environment variable for client secret |
| `api_key_env` | `Optional[str]` | `None` | Environment variable for API key fallback |
| `scopes` | `List[str]` | `[]` | OAuth scopes to request |
| `redirect_uri` | `str` | `"urn:ietf:wg:oauth:2.0:oob"` | Redirect URI for auth code flow |
| `account_id` | `Optional[str]` | `None` | Account ID for client credentials grant (direct value) |
| `account_id_env` | `Optional[str]` | `None` | Environment variable for account ID |
| `token_path` | `Optional[Path]` | `None` | Custom token storage path |

### Resolved Properties

These properties resolve values by checking the direct field first, then falling back to the environment variable.

| Property | Return Type | Description |
|---|---|---|
| `resolved_client_id` | `Optional[str]` | Client ID from `client_id` or `os.environ[client_id_env]` |
| `resolved_client_secret` | `Optional[str]` | Client secret from `client_secret` or `os.environ[client_secret_env]` |
| `resolved_api_key` | `Optional[str]` | API key from `os.environ[api_key_env]` |
| `resolved_account_id` | `Optional[str]` | Account ID from `account_id` or `os.environ[account_id_env]` |
| `resolved_token_path` | `Path` | Token file path: `token_path` or `~/.planopticon/{service}_token.json` |
| `supports_oauth` | `bool` | `True` if both `oauth_authorize_url` and `oauth_token_url` are set |

```python
from video_processor.auth import AuthConfig

config = AuthConfig(
    service="notion",
    oauth_authorize_url="https://api.notion.com/v1/oauth/authorize",
    oauth_token_url="https://api.notion.com/v1/oauth/token",
    client_id_env="NOTION_CLIENT_ID",
    client_secret_env="NOTION_CLIENT_SECRET",
    api_key_env="NOTION_API_KEY",
    scopes=["read_content"],
)

# Check resolved values
print(config.resolved_client_id)   # From NOTION_CLIENT_ID env var
print(config.supports_oauth)       # True
print(config.resolved_token_path)  # ~/.planopticon/notion_token.json
```

---

## AuthResult

```python
from video_processor.auth import AuthResult
```

Dataclass representing the result of an authentication attempt.

| Field | Type | Default | Description |
|---|---|---|---|
| `success` | `bool` | *required* | Whether authentication succeeded |
| `access_token` | `Optional[str]` | `None` | The access token (if successful) |
| `method` | `Optional[str]` | `None` | Auth method used: `"saved_token"`, `"oauth_pkce"`, `"client_credentials"`, `"api_key"` |
| `expires_at` | `Optional[float]` | `None` | Token expiration as Unix timestamp |
| `refresh_token` | `Optional[str]` | `None` | OAuth refresh token (if available) |
| `error` | `Optional[str]` | `None` | Error message (if failed) |

```python
result = manager.authenticate()
if result.success:
    print(f"Authenticated via {result.method}")
    print(f"Token: {result.access_token[:20]}...")
    if result.expires_at:
        import time
        remaining = result.expires_at - time.time()
        print(f"Expires in {remaining/60:.0f} minutes")
else:
    print(f"Auth failed: {result.error}")
```

---

## OAuthManager

```python
from video_processor.auth import OAuthManager
```

Manages the full authentication lifecycle for a service. Tries auth methods in priority order and handles token persistence, refresh, and PKCE flow.

### Constructor

```python
def __init__(self, config: AuthConfig)
```

| Parameter | Type | Description |
|---|---|---|
| `config` | `AuthConfig` | Authentication configuration for the target service |

### authenticate()

```python
def authenticate(self) -> AuthResult
```

Run the full auth chain and return the result. Methods are tried in order:

1. **Saved token** -- checks `~/.planopticon/{service}_token.json`, refreshes if expired
2. **Client Credentials** -- if `account_id` is set and OAuth is configured, uses the client credentials grant (server-to-server)
3. **OAuth PKCE** -- if OAuth is configured and client ID is available, opens a browser for interactive authorization with PKCE
4. **API key** -- falls back to the environment variable specified in `api_key_env`

**Returns:** `AuthResult` -- success/failure with token and method details.

If all methods fail, returns an `AuthResult` with `success=False` and a helpful error message listing which environment variables to set.

### get_token()

```python
def get_token(self) -> Optional[str]
```

Convenience method: run `authenticate()` and return just the access token string.

**Returns:** `Optional[str]` -- the access token, or `None` if authentication failed.

### clear_token()

```python
def clear_token(self) -> None
```

Remove the saved token file for this service (effectively a logout). The next `authenticate()` call will require re-authentication.

---

## Authentication Flows

### Saved Token (auto-refresh)

Tokens are saved to `~/.planopticon/{service}_token.json` as JSON. On each `authenticate()` call, the saved token is loaded and checked:

- If the token has not expired (`time.time() < expires_at`), it is returned immediately
- If expired but a refresh token is available, the manager attempts to refresh using the OAuth token endpoint
- The refreshed token is saved back to disk

### Client Credentials Grant

Used for server-to-server authentication (e.g., Zoom Server-to-Server OAuth). Requires `account_id`, `client_id`, and `client_secret`. Sends a POST to the token endpoint with `grant_type=account_credentials`.

### OAuth 2.0 Authorization Code with PKCE

Interactive flow for user authentication:

1. Generates a PKCE code verifier and S256 challenge
2. Constructs the authorization URL with client ID, redirect URI, scopes, and PKCE challenge
3. Opens the URL in the user's browser
4. Prompts the user to paste the authorization code
5. Exchanges the code for tokens at the token endpoint
6. Saves the tokens to disk

### API Key Fallback

If no OAuth flow succeeds, falls back to checking the environment variable specified in `api_key_env`. Returns the value directly as the access token.

---

## KNOWN_CONFIGS

```python
from video_processor.auth import KNOWN_CONFIGS
```

Pre-built `AuthConfig` instances for supported services. These cover the most common cloud integrations and can be used directly or as templates for custom configurations.

| Service Key | Service | OAuth Endpoints | Client ID Env | API Key Env |
|---|---|---|---|---|
| `"zoom"` | Zoom | `zoom.us/oauth/...` | `ZOOM_CLIENT_ID` | -- |
| `"notion"` | Notion | `api.notion.com/v1/oauth/...` | `NOTION_CLIENT_ID` | `NOTION_API_KEY` |
| `"dropbox"` | Dropbox | `dropbox.com/oauth2/...` | `DROPBOX_APP_KEY` | `DROPBOX_ACCESS_TOKEN` |
| `"github"` | GitHub | `github.com/login/oauth/...` | `GITHUB_CLIENT_ID` | `GITHUB_TOKEN` |
| `"google"` | Google | `accounts.google.com/o/oauth2/...` | `GOOGLE_CLIENT_ID` | `GOOGLE_API_KEY` |
| `"microsoft"` | Microsoft | `login.microsoftonline.com/.../oauth2/...` | `MICROSOFT_CLIENT_ID` | -- |

### Zoom

Supports both Server-to-Server (via `ZOOM_ACCOUNT_ID`) and OAuth PKCE flows.

```bash
# Server-to-Server
export ZOOM_CLIENT_ID="..."
export ZOOM_CLIENT_SECRET="..."
export ZOOM_ACCOUNT_ID="..."

# Or interactive OAuth (omit ZOOM_ACCOUNT_ID)
export ZOOM_CLIENT_ID="..."
export ZOOM_CLIENT_SECRET="..."
```

### Google (Drive, Meet, Workspace)

Supports OAuth PKCE and API key fallback. Scopes include Drive and Docs read-only access.

```bash
export GOOGLE_CLIENT_ID="..."
export GOOGLE_CLIENT_SECRET="..."
# Or for API-key-only access:
export GOOGLE_API_KEY="..."
```

### GitHub

Supports OAuth PKCE and personal access token. Requests `repo` and `read:org` scopes.

```bash
# OAuth
export GITHUB_CLIENT_ID="..."
export GITHUB_CLIENT_SECRET="..."
# Or personal access token
export GITHUB_TOKEN="ghp_..."
```

---

## Helper Functions

### get_auth_config()

```python
def get_auth_config(service: str) -> Optional[AuthConfig]
```

Get a pre-built `AuthConfig` for a known service.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `service` | `str` | Service name (e.g., `"zoom"`, `"notion"`, `"github"`) |

**Returns:** `Optional[AuthConfig]` -- the config, or `None` if the service is not in `KNOWN_CONFIGS`.

### get_auth_manager()

```python
def get_auth_manager(service: str) -> Optional[OAuthManager]
```

Get an `OAuthManager` for a known service. Convenience wrapper that looks up the config and creates the manager in one call.

**Returns:** `Optional[OAuthManager]` -- the manager, or `None` if the service is not known.

---

## Usage Examples

### Quick authentication for a known service

```python
from video_processor.auth import get_auth_manager

manager = get_auth_manager("zoom")
if manager:
    result = manager.authenticate()
    if result.success:
        print(f"Authenticated via {result.method}")
        # Use result.access_token for API calls
    else:
        print(f"Failed: {result.error}")
```

### Custom service configuration

```python
from video_processor.auth import AuthConfig, OAuthManager

config = AuthConfig(
    service="my_service",
    oauth_authorize_url="https://my-service.com/oauth/authorize",
    oauth_token_url="https://my-service.com/oauth/token",
    client_id_env="MY_SERVICE_CLIENT_ID",
    client_secret_env="MY_SERVICE_CLIENT_SECRET",
    api_key_env="MY_SERVICE_API_KEY",
    scopes=["read", "write"],
)

manager = OAuthManager(config)
token = manager.get_token()  # Returns str or None
```

### Using auth in a custom source connector

```python
from pathlib import Path
from typing import List, Optional

from video_processor.auth import OAuthManager, AuthConfig
from video_processor.sources.base import BaseSource, SourceFile

class CustomSource(BaseSource):
    def __init__(self):
        self._config = AuthConfig(
            service="custom",
            api_key_env="CUSTOM_API_KEY",
        )
        self._manager = OAuthManager(self._config)
        self._token: Optional[str] = None

    def authenticate(self) -> bool:
        self._token = self._manager.get_token()
        return self._token is not None

    def list_videos(self, **kwargs) -> List[SourceFile]:
        # Use self._token to query the API
        ...

    def download(self, file: SourceFile, destination: Path) -> Path:
        # Use self._token for authenticated downloads
        ...
```

### Logout / clear saved token

```python
from video_processor.auth import get_auth_manager

manager = get_auth_manager("zoom")
if manager:
    manager.clear_token()
    print("Zoom token cleared")
```

### Token storage location

All tokens are stored under `~/.planopticon/`:

```
~/.planopticon/
    zoom_token.json
    notion_token.json
    github_token.json
    google_token.json
    microsoft_token.json
    dropbox_token.json
```

Each file contains a JSON object with `access_token`, `refresh_token` (if applicable), `expires_at`, and client credentials for refresh.
