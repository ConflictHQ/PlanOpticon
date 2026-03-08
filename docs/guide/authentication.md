# Authentication

PlanOpticon uses a unified authentication system to connect with cloud services for fetching recordings, documents, and other content. The system is **OAuth-first**: it prefers OAuth 2.0 flows for security and token management, but falls back to API keys when OAuth is not configured.

## Auth strategy overview

PlanOpticon supports six cloud services out of the box: Google, Dropbox, Zoom, Notion, GitHub, and Microsoft. Each service uses the same authentication chain, implemented through the `OAuthManager` class. You configure credentials once (via environment variables or directly), and PlanOpticon handles token acquisition, storage, refresh, and fallback automatically.

All authentication state is managed through the `planopticon auth` CLI command, the `/auth` companion REPL command, or programmatically via the Python API.

## The auth chain

When you authenticate with a service, PlanOpticon tries the following methods in order. It stops at the first one that succeeds:

1. **Saved token** -- Checks `~/.planopticon/{service}_token.json` for a previously saved token. If the token has not expired, it is used immediately. If it has expired but a refresh token is available, PlanOpticon attempts an automatic token refresh.

2. **Client Credentials grant** (Server-to-Server) -- If an `account_id` is configured (e.g., `ZOOM_ACCOUNT_ID`), PlanOpticon attempts a client credentials grant. This is a non-interactive flow suitable for automated pipelines and server-side integrations. No browser is required.

3. **OAuth 2.0 Authorization Code with PKCE** (interactive) -- If a client ID is configured and OAuth endpoints are available, PlanOpticon initiates an interactive OAuth PKCE flow. It opens a browser to the service's authorization page, waits for you to paste the authorization code, and exchanges it for tokens. The tokens are saved for future use.

4. **API key fallback** -- If no OAuth method succeeds, PlanOpticon checks for a service-specific API key environment variable (e.g., `GITHUB_TOKEN`, `NOTION_API_KEY`). This is the simplest setup but may have reduced capabilities compared to OAuth.

If none of the four methods succeed, PlanOpticon returns an error with hints about which environment variables to set.

## Token storage

Tokens are persisted as JSON files in `~/.planopticon/`:

```
~/.planopticon/
  google_token.json
  dropbox_token.json
  zoom_token.json
  notion_token.json
  github_token.json
  microsoft_token.json
```

Each token file contains:

| Field | Description |
|-------|-------------|
| `access_token` | The current access token |
| `refresh_token` | Refresh token for automatic renewal (if provided by the service) |
| `expires_at` | Unix timestamp when the token expires (with a 60-second safety margin) |
| `client_id` | The client ID used for this token (for refresh) |
| `client_secret` | The client secret used (for refresh) |

The `~/.planopticon/` directory is created automatically on first use. Token files are overwritten on each successful authentication or refresh.

To remove a saved token, use `planopticon auth <service> --logout` or delete the file directly.

## Supported services

### Google

Google authentication provides access to Google Drive and Google Docs for fetching documents, recordings, and other content.

**Scopes requested:**

- `https://www.googleapis.com/auth/drive.readonly`
- `https://www.googleapis.com/auth/documents.readonly`

**Environment variables:**

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_CLIENT_ID` | For OAuth | OAuth 2.0 Client ID from Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | For OAuth | OAuth 2.0 Client Secret |
| `GOOGLE_API_KEY` | Fallback | API key (limited access, no user-specific data) |

**OAuth app setup:**

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project (or select an existing one).
3. Navigate to **APIs & Services > Credentials**.
4. Click **Create Credentials > OAuth client ID**.
5. Choose **Desktop app** as the application type.
6. Copy the Client ID and Client Secret.
7. Under **APIs & Services > Library**, enable the **Google Drive API** and **Google Docs API**.
8. Set the environment variables:

```bash
export GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="your-client-secret"
```

**Service account fallback:** For automated pipelines, you can use a Google service account instead of OAuth. Generate a service account key JSON file from the Google Cloud Console and set `GOOGLE_APPLICATION_CREDENTIALS` to point to it. The PlanOpticon Google Workspace connector (`planopticon gws`) uses the `gws` CLI which has its own auth flow via `gws auth login`.

### Dropbox

Dropbox authentication provides access to files stored in Dropbox.

**Environment variables:**

| Variable | Required | Description |
|----------|----------|-------------|
| `DROPBOX_APP_KEY` | For OAuth | App key from the Dropbox App Console |
| `DROPBOX_APP_SECRET` | For OAuth | App secret |
| `DROPBOX_ACCESS_TOKEN` | Fallback | Long-lived access token (for quick setup) |

**OAuth app setup:**

1. Go to the [Dropbox App Console](https://www.dropbox.com/developers/apps).
2. Click **Create App**.
3. Choose **Scoped access** and **Full Dropbox** (or **App folder** for restricted access).
4. Copy the App key and App secret from the **Settings** tab.
5. Set the environment variables:

```bash
export DROPBOX_APP_KEY="your-app-key"
export DROPBOX_APP_SECRET="your-app-secret"
```

**Access token shortcut:** For quick testing, you can generate an access token directly from the app's Settings page in the Dropbox App Console and set it as `DROPBOX_ACCESS_TOKEN`. This bypasses OAuth entirely but the token may have a limited lifetime.

### Zoom

Zoom authentication provides access to cloud recordings, meeting metadata, and transcripts.

**Environment variables:**

| Variable | Required | Description |
|----------|----------|-------------|
| `ZOOM_CLIENT_ID` | For OAuth | OAuth client ID from the Zoom Marketplace |
| `ZOOM_CLIENT_SECRET` | For OAuth | OAuth client secret |
| `ZOOM_ACCOUNT_ID` | For S2S | Account ID for Server-to-Server OAuth |

**Server-to-Server (recommended for automation):**

When `ZOOM_ACCOUNT_ID` is set alongside `ZOOM_CLIENT_ID` and `ZOOM_CLIENT_SECRET`, PlanOpticon uses the client credentials grant (Server-to-Server OAuth). This is non-interactive and ideal for CI/CD pipelines and scheduled jobs.

1. Go to the [Zoom Marketplace](https://marketplace.zoom.us/).
2. Click **Develop > Build App**.
3. Choose **Server-to-Server OAuth**.
4. Copy the Account ID, Client ID, and Client Secret.
5. Add the required scopes: `recording:read:admin` (or `recording:read`).
6. Set the environment variables:

```bash
export ZOOM_CLIENT_ID="your-client-id"
export ZOOM_CLIENT_SECRET="your-client-secret"
export ZOOM_ACCOUNT_ID="your-account-id"
```

**User-level OAuth PKCE:**

If `ZOOM_ACCOUNT_ID` is not set, PlanOpticon falls back to the interactive OAuth PKCE flow. This opens a browser window for the user to authorize access.

1. In the Zoom Marketplace, create a **General App** (or **OAuth** app).
2. Set the redirect URI to `urn:ietf:wg:oauth:2.0:oob` (out-of-band).
3. Copy the Client ID and Client Secret.

### Notion

Notion authentication provides access to pages, databases, and content in your Notion workspace.

**Environment variables:**

| Variable | Required | Description |
|----------|----------|-------------|
| `NOTION_CLIENT_ID` | For OAuth | OAuth client ID from the Notion Integrations page |
| `NOTION_CLIENT_SECRET` | For OAuth | OAuth client secret |
| `NOTION_API_KEY` | Fallback | Internal integration token |

**OAuth app setup:**

1. Go to [My Integrations](https://www.notion.so/my-integrations) in Notion.
2. Click **New integration**.
3. Select **Public integration** (required for OAuth).
4. Copy the OAuth Client ID and Client Secret.
5. Set the redirect URI.
6. Set the environment variables:

```bash
export NOTION_CLIENT_ID="your-client-id"
export NOTION_CLIENT_SECRET="your-client-secret"
```

**Internal integration (API key fallback):**

For simpler setups, create an **Internal integration** from the Notion Integrations page. Copy the integration token and set it as `NOTION_API_KEY`. You must also share the relevant Notion pages/databases with the integration.

```bash
export NOTION_API_KEY="ntn_your-integration-token"
```

### GitHub

GitHub authentication provides access to repositories, issues, and organization data.

**Scopes requested:**

- `repo`
- `read:org`

**Environment variables:**

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_CLIENT_ID` | For OAuth | OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | For OAuth | OAuth App client secret |
| `GITHUB_TOKEN` | Fallback | Personal access token (classic or fine-grained) |

**OAuth app setup:**

1. Go to **GitHub > Settings > Developer Settings > OAuth Apps**.
2. Click **New OAuth App**.
3. Set the Authorization callback URL to `urn:ietf:wg:oauth:2.0:oob`.
4. Copy the Client ID and generate a Client Secret.
5. Set the environment variables:

```bash
export GITHUB_CLIENT_ID="your-client-id"
export GITHUB_CLIENT_SECRET="your-client-secret"
```

**Personal access token (recommended for most users):**

The simplest approach is to create a Personal Access Token:

1. Go to **GitHub > Settings > Developer Settings > Personal Access Tokens**.
2. Generate a token with `repo` and `read:org` scopes.
3. Set it as `GITHUB_TOKEN`:

```bash
export GITHUB_TOKEN="ghp_your-token"
```

### Microsoft

Microsoft authentication provides access to Microsoft 365 resources via the Microsoft Graph API, including OneDrive, SharePoint, and Teams recordings.

**Scopes requested:**

- `https://graph.microsoft.com/OnlineMeetings.Read`
- `https://graph.microsoft.com/Files.Read`

**Environment variables:**

| Variable | Required | Description |
|----------|----------|-------------|
| `MICROSOFT_CLIENT_ID` | For OAuth | Application (client) ID from Azure AD |
| `MICROSOFT_CLIENT_SECRET` | For OAuth | Client secret from Azure AD |

**Azure AD app registration:**

1. Go to the [Azure Portal](https://portal.azure.com/).
2. Navigate to **Azure Active Directory > App registrations**.
3. Click **New registration**.
4. Name the application (e.g., "PlanOpticon").
5. Under **Supported account types**, select the appropriate option for your organization.
6. Set the redirect URI to `urn:ietf:wg:oauth:2.0:oob` with platform **Mobile and desktop applications**.
7. After registration, go to **Certificates & secrets** and create a new client secret.
8. Under **API permissions**, add:
    - `OnlineMeetings.Read`
    - `Files.Read`
9. Grant admin consent if required by your organization.
10. Set the environment variables:

```bash
export MICROSOFT_CLIENT_ID="your-application-id"
export MICROSOFT_CLIENT_SECRET="your-client-secret"
```

**Microsoft 365 CLI:** The `planopticon m365` commands use the `@pnp/cli-microsoft365` npm package, which has its own authentication flow via `m365 login`. This is separate from the OAuth flow described above.

## CLI usage

### `planopticon auth`

Authenticate with a cloud service or manage saved tokens.

```
planopticon auth SERVICE [--logout]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `SERVICE` | One of: `google`, `dropbox`, `zoom`, `notion`, `github`, `microsoft` |

**Options:**

| Option | Description |
|--------|-------------|
| `--logout` | Clear the saved token for the specified service |

**Examples:**

```bash
# Authenticate with Google (triggers OAuth flow or uses saved token)
planopticon auth google

# Authenticate with Zoom
planopticon auth zoom

# Clear saved GitHub token
planopticon auth github --logout
```

On success, the command prints the authentication method used:

```
Google authentication successful (oauth_pkce).
```

or

```
Github authentication successful (api_key).
```

### Companion REPL `/auth`

Inside the interactive companion REPL (`planopticon -C` or `planopticon -I`), you can authenticate with services using the `/auth` command:

```
/auth SERVICE
```

Without arguments, `/auth` lists all available services:

```
> /auth
Usage: /auth SERVICE
Available: dropbox, github, google, microsoft, notion, zoom
```

With a service name, it runs the same auth chain as the CLI command:

```
> /auth github
Github authentication successful (api_key).
```

## Environment variables reference

The following table summarizes all environment variables used by the authentication system:

| Service | OAuth Client ID | OAuth Client Secret | API Key / Token | Account ID |
|---------|----------------|--------------------|--------------------|------------|
| Google | `GOOGLE_CLIENT_ID` | `GOOGLE_CLIENT_SECRET` | `GOOGLE_API_KEY` | -- |
| Dropbox | `DROPBOX_APP_KEY` | `DROPBOX_APP_SECRET` | `DROPBOX_ACCESS_TOKEN` | -- |
| Zoom | `ZOOM_CLIENT_ID` | `ZOOM_CLIENT_SECRET` | -- | `ZOOM_ACCOUNT_ID` |
| Notion | `NOTION_CLIENT_ID` | `NOTION_CLIENT_SECRET` | `NOTION_API_KEY` | -- |
| GitHub | `GITHUB_CLIENT_ID` | `GITHUB_CLIENT_SECRET` | `GITHUB_TOKEN` | -- |
| Microsoft | `MICROSOFT_CLIENT_ID` | `MICROSOFT_CLIENT_SECRET` | -- | -- |

## Python API

### AuthConfig

The `AuthConfig` dataclass defines the authentication configuration for a service. It holds OAuth endpoints, credential references, scopes, and token storage paths.

```python
from video_processor.auth import AuthConfig

config = AuthConfig(
    service="myservice",
    oauth_authorize_url="https://example.com/oauth/authorize",
    oauth_token_url="https://example.com/oauth/token",
    client_id_env="MYSERVICE_CLIENT_ID",
    client_secret_env="MYSERVICE_CLIENT_SECRET",
    api_key_env="MYSERVICE_API_KEY",
    scopes=["read", "write"],
)
```

**Key fields:**

| Field | Type | Description |
|-------|------|-------------|
| `service` | `str` | Service identifier (used for token filename) |
| `oauth_authorize_url` | `Optional[str]` | OAuth authorization endpoint |
| `oauth_token_url` | `Optional[str]` | OAuth token endpoint |
| `client_id` / `client_id_env` | `Optional[str]` | Client ID value or env var name |
| `client_secret` / `client_secret_env` | `Optional[str]` | Client secret value or env var name |
| `api_key_env` | `Optional[str]` | Environment variable for API key fallback |
| `scopes` | `List[str]` | OAuth scopes to request |
| `redirect_uri` | `str` | Redirect URI (default: `urn:ietf:wg:oauth:2.0:oob`) |
| `account_id` / `account_id_env` | `Optional[str]` | Account ID for client credentials grant |
| `token_path` | `Optional[Path]` | Override token storage path |

**Resolved properties:**

- `resolved_client_id` -- Returns the client ID from the direct value or environment variable.
- `resolved_client_secret` -- Returns the client secret from the direct value or environment variable.
- `resolved_api_key` -- Returns the API key from the environment variable.
- `resolved_account_id` -- Returns the account ID from the direct value or environment variable.
- `resolved_token_path` -- Returns the token file path (default: `~/.planopticon/{service}_token.json`).
- `supports_oauth` -- Returns `True` if both OAuth endpoints are configured.

### OAuthManager

The `OAuthManager` class manages the full authentication lifecycle for a service.

```python
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

# Full auth chain -- returns AuthResult
result = manager.authenticate()
if result.success:
    print(f"Authenticated via {result.method}")
    print(f"Token: {result.access_token[:20]}...")

# Convenience method -- returns just the token string or None
token = manager.get_token()

# Clear saved token (logout)
manager.clear_token()
```

**AuthResult fields:**

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | Whether authentication succeeded |
| `access_token` | `Optional[str]` | The access token (if successful) |
| `method` | `Optional[str]` | One of: `saved_token`, `oauth_pkce`, `client_credentials`, `api_key` |
| `expires_at` | `Optional[float]` | Token expiry as a Unix timestamp |
| `refresh_token` | `Optional[str]` | Refresh token (if provided) |
| `error` | `Optional[str]` | Error message (if unsuccessful) |

### Pre-built configs

PlanOpticon ships with pre-built `AuthConfig` instances for all six supported services. Access them via convenience functions:

```python
from video_processor.auth import get_auth_config, get_auth_manager

# Get just the config
config = get_auth_config("zoom")

# Get a ready-to-use manager
manager = get_auth_manager("github")
token = manager.get_token()
```

### Building custom connectors

To add authentication for a new service, create an `AuthConfig` with the service's OAuth endpoints and credential environment variables:

```python
from video_processor.auth import AuthConfig, OAuthManager

config = AuthConfig(
    service="slack",
    oauth_authorize_url="https://slack.com/oauth/v2/authorize",
    oauth_token_url="https://slack.com/api/oauth.v2.access",
    client_id_env="SLACK_CLIENT_ID",
    client_secret_env="SLACK_CLIENT_SECRET",
    api_key_env="SLACK_BOT_TOKEN",
    scopes=["channels:read", "channels:history"],
)

manager = OAuthManager(config)
result = manager.authenticate()
```

The token will be saved to `~/.planopticon/slack_token.json` and automatically refreshed on subsequent calls.

## Troubleshooting

### "No auth method available for {service}"

This means none of the four auth methods succeeded. Check that:

- The required environment variables are set and non-empty.
- For OAuth: both the client ID and client secret (or app key/secret) are set.
- For API key fallback: the correct environment variable is set.

The error message includes hints about which variables to set.

### Token refresh fails

If automatic token refresh fails, PlanOpticon falls back to the next auth method in the chain. Common causes:

- The refresh token has been revoked (e.g., you changed your password or revoked app access).
- The OAuth app's client secret has changed.
- The service requires re-authorization after a certain period.

To resolve, clear the token and re-authenticate:

```bash
planopticon auth google --logout
planopticon auth google
```

### OAuth PKCE flow does not open a browser

If the browser does not open automatically, PlanOpticon prints the authorization URL to the terminal. Copy and paste it into your browser manually. After authorizing, paste the authorization code back into the terminal prompt.

### "requests not installed"

The OAuth flows require the `requests` library. It is included as a dependency of PlanOpticon, but if you installed PlanOpticon in a minimal environment, install it manually:

```bash
pip install requests
```

### Permission denied on token file

PlanOpticon needs write access to `~/.planopticon/`. If the directory or token files have restrictive permissions, adjust them:

```bash
chmod 700 ~/.planopticon
chmod 600 ~/.planopticon/*_token.json
```

### Microsoft authentication uses the `/common` tenant

The default Microsoft OAuth configuration uses the `common` tenant endpoint (`login.microsoftonline.com/common/...`), which supports both personal Microsoft accounts and Azure AD organizational accounts. If your organization requires a specific tenant, you can create a custom `AuthConfig` with the tenant-specific URLs.
