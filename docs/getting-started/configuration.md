# Configuration

## Example `.env` file

Create a `.env` file in your project directory. PlanOpticon loads it automatically.

```bash
# =============================================================================
# PlanOpticon Configuration
# =============================================================================
# Copy this file to .env and fill in the values you need.
# You only need ONE AI provider — PlanOpticon auto-detects which are available.

# --- AI Providers (set at least one) ----------------------------------------

# OpenAI — get your key at https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-...

# Anthropic — get your key at https://console.anthropic.com/settings/keys
ANTHROPIC_API_KEY=sk-ant-...

# Google Gemini — get your key at https://aistudio.google.com/apikey
GEMINI_API_KEY=AI...

# Azure OpenAI — from your Azure portal deployment
# AZURE_OPENAI_API_KEY=...
# AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/

# Together AI — https://api.together.xyz/settings/api-keys
# TOGETHER_API_KEY=...

# Fireworks AI — https://fireworks.ai/account/api-keys
# FIREWORKS_API_KEY=...

# Cerebras — https://cloud.cerebras.ai/
# CEREBRAS_API_KEY=...

# xAI (Grok) — https://console.x.ai/
# XAI_API_KEY=...

# Ollama (local, no key needed) — just run: ollama serve
# OLLAMA_HOST=http://localhost:11434

# --- Google (Drive, Docs, Sheets, Meet, YouTube) ----------------------------
# Option A: OAuth (interactive, recommended for personal use)
# Create credentials at https://console.cloud.google.com/apis/credentials
# 1. Create an OAuth 2.0 Client ID (Desktop application)
# 2. Enable these APIs: Google Drive API, Google Docs API
GOOGLE_CLIENT_ID=123456789-abc.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-...

# Option B: Service Account (automated/server-side)
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# --- Zoom (recordings) ------------------------------------------------------
# Create an OAuth app at https://marketplace.zoom.us/develop/create
# App type: "General App" with OAuth
# Scopes: cloud_recording:read:list_user_recordings, cloud_recording:read:recording
ZOOM_CLIENT_ID=...
ZOOM_CLIENT_SECRET=...
# For Server-to-Server (no browser needed):
# ZOOM_ACCOUNT_ID=...

# --- Microsoft 365 (OneDrive, SharePoint, Teams) ----------------------------
# Register an app at https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps
# API permissions: OnlineMeetings.Read, Files.Read (delegated)
MICROSOFT_CLIENT_ID=...
MICROSOFT_CLIENT_SECRET=...

# --- Notion ------------------------------------------------------------------
# Option A: OAuth (create integration at https://www.notion.so/my-integrations)
# NOTION_CLIENT_ID=...
# NOTION_CLIENT_SECRET=...

# Option B: API key (simpler, from the same integrations page)
NOTION_API_KEY=secret_...

# --- GitHub ------------------------------------------------------------------
# Option A: Personal Access Token (simplest)
# Create at https://github.com/settings/tokens — needs 'repo' scope
GITHUB_TOKEN=ghp_...

# Option B: OAuth App (for CI/automation)
# GITHUB_CLIENT_ID=...
# GITHUB_CLIENT_SECRET=...

# --- Dropbox -----------------------------------------------------------------
# Create an app at https://www.dropbox.com/developers/apps
# DROPBOX_APP_KEY=...
# DROPBOX_APP_SECRET=...
# Or use a long-lived access token:
# DROPBOX_ACCESS_TOKEN=...

# --- General -----------------------------------------------------------------
# CACHE_DIR=~/.cache/planopticon
```

## Environment variables reference

### AI providers

| Variable | Required | Where to get it |
|----------|----------|----------------|
| `OPENAI_API_KEY` | At least one provider | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `ANTHROPIC_API_KEY` | At least one provider | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| `GEMINI_API_KEY` | At least one provider | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| `AZURE_OPENAI_API_KEY` | Optional | Azure portal > your OpenAI resource |
| `AZURE_OPENAI_ENDPOINT` | With Azure | Azure portal > your OpenAI resource |
| `TOGETHER_API_KEY` | Optional | [api.together.xyz](https://api.together.xyz/settings/api-keys) |
| `FIREWORKS_API_KEY` | Optional | [fireworks.ai](https://fireworks.ai/account/api-keys) |
| `CEREBRAS_API_KEY` | Optional | [cloud.cerebras.ai](https://cloud.cerebras.ai/) |
| `XAI_API_KEY` | Optional | [console.x.ai](https://console.x.ai/) |
| `OLLAMA_HOST` | Optional | Default: `http://localhost:11434` |

### Cloud services

| Variable | Service | Auth method |
|----------|---------|-------------|
| `GOOGLE_CLIENT_ID` | Google (Drive, Docs, Meet) | OAuth |
| `GOOGLE_CLIENT_SECRET` | Google | OAuth |
| `GOOGLE_APPLICATION_CREDENTIALS` | Google | Service account |
| `ZOOM_CLIENT_ID` | Zoom | OAuth |
| `ZOOM_CLIENT_SECRET` | Zoom | OAuth |
| `ZOOM_ACCOUNT_ID` | Zoom | Server-to-Server |
| `MICROSOFT_CLIENT_ID` | Microsoft 365 | OAuth |
| `MICROSOFT_CLIENT_SECRET` | Microsoft 365 | OAuth |
| `NOTION_CLIENT_ID` | Notion | OAuth |
| `NOTION_CLIENT_SECRET` | Notion | OAuth |
| `NOTION_API_KEY` | Notion | API key |
| `GITHUB_CLIENT_ID` | GitHub | OAuth |
| `GITHUB_CLIENT_SECRET` | GitHub | OAuth |
| `GITHUB_TOKEN` | GitHub | API key |
| `DROPBOX_APP_KEY` | Dropbox | OAuth |
| `DROPBOX_APP_SECRET` | Dropbox | OAuth |
| `DROPBOX_ACCESS_TOKEN` | Dropbox | API key |

### General

| Variable | Description |
|----------|-------------|
| `CACHE_DIR` | Directory for API response caching |

## Authentication

PlanOpticon uses OAuth for cloud services. Run `planopticon auth` once per service — tokens are saved locally and refreshed automatically.

```bash
planopticon auth google      # Google Drive, Docs, Meet, YouTube
planopticon auth dropbox     # Dropbox
planopticon auth zoom        # Zoom recordings
planopticon auth notion      # Notion pages
planopticon auth github      # GitHub repos and wikis
planopticon auth microsoft   # OneDrive, SharePoint, Teams
```

Credentials are stored in `~/.planopticon/`. Use `planopticon auth SERVICE --logout` to remove them.

### What each service needs

| Service | Minimum setup | Full OAuth setup |
|---------|--------------|-----------------|
| Google | `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` | Create OAuth credentials in [Google Cloud Console](https://console.cloud.google.com/apis/credentials) |
| Zoom | `ZOOM_CLIENT_ID` + `ZOOM_CLIENT_SECRET` | Create a General App at [marketplace.zoom.us](https://marketplace.zoom.us/develop/create) |
| Microsoft | `MICROSOFT_CLIENT_ID` + `MICROSOFT_CLIENT_SECRET` | Register app in [Azure AD](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps) |
| Notion | `NOTION_API_KEY` (simplest) | Create integration at [notion.so/my-integrations](https://www.notion.so/my-integrations) |
| GitHub | `GITHUB_TOKEN` (simplest) | Create token at [github.com/settings/tokens](https://github.com/settings/tokens) |
| Dropbox | `DROPBOX_APP_KEY` + `DROPBOX_APP_SECRET` | Create app at [dropbox.com/developers](https://www.dropbox.com/developers/apps) |

For detailed OAuth app creation walkthroughs, see the [Authentication guide](../guide/authentication.md).

## Provider routing

PlanOpticon auto-discovers available models and routes each task to the cheapest capable option:

| Task | Default preference |
|------|--------------------|
| Vision (diagrams) | Gemini Flash > GPT-4o-mini > Claude Haiku > Ollama |
| Chat (analysis) | Claude Haiku > GPT-4o-mini > Gemini Flash > Ollama |
| Transcription | Local Whisper > Whisper-1 > Gemini Flash |

Default models prioritize cost efficiency. For complex or high-stakes analysis, override with more capable models using `--chat-model` or `--vision-model`.

If no cloud API keys are configured, PlanOpticon automatically falls back to Ollama when a local server is running. This enables fully offline operation when paired with local Whisper for transcription.

Override with `--provider`, `--vision-model`, or `--chat-model` flags.

## Frame sampling

Control how frames are extracted:

```bash
# Sample rate: frames per second (default: 0.5)
planopticon analyze -i video.mp4 -o ./out --sampling-rate 1.0

# Change threshold: visual difference needed to keep a frame (default: 0.15)
planopticon analyze -i video.mp4 -o ./out --change-threshold 0.1

# Periodic capture: capture a frame every N seconds regardless of change (default: 30)
# Useful for slow-evolving content like document scrolling
planopticon analyze -i video.mp4 -o ./out --periodic-capture 15

# Disable periodic capture (rely only on change detection)
planopticon analyze -i video.mp4 -o ./out --periodic-capture 0
```

Lower `change-threshold` = more frames kept. Higher `sampling-rate` = more candidates. Periodic capture catches content that changes too slowly for change detection (e.g., scrolling through a document during a screen share).

People/webcam frames are automatically filtered out using face detection — no configuration needed.

## Focus areas

Limit processing to specific extraction types:

```bash
planopticon analyze -i video.mp4 -o ./out --focus "diagrams,action-items"
```

## GPU acceleration

```bash
planopticon analyze -i video.mp4 -o ./out --use-gpu
```

Requires `planopticon[gpu]` extras installed.
