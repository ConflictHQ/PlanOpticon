# Configuration

## Environment variables

### AI providers

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GEMINI_API_KEY` | Google Gemini API key |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL |
| `TOGETHER_API_KEY` | Together AI API key |
| `FIREWORKS_API_KEY` | Fireworks AI API key |
| `CEREBRAS_API_KEY` | Cerebras API key |
| `XAI_API_KEY` | xAI (Grok) API key |
| `OLLAMA_HOST` | Ollama server URL (default: `http://localhost:11434`) |

### Cloud services

| Variable | Description |
|----------|-------------|
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to Google service account JSON (for server-side Drive access) |
| `ZOOM_CLIENT_ID` | Zoom OAuth app client ID |
| `ZOOM_CLIENT_SECRET` | Zoom OAuth app client secret |
| `NOTION_API_KEY` | Notion integration token |
| `GITHUB_TOKEN` | GitHub personal access token |
| `MICROSOFT_CLIENT_ID` | Azure AD app client ID (for Microsoft 365) |
| `MICROSOFT_CLIENT_SECRET` | Azure AD app client secret |

### General

| Variable | Description |
|----------|-------------|
| `CACHE_DIR` | Directory for API response caching |

## Authentication

Most cloud services use OAuth via the `planopticon auth` command. Run it once per service to store credentials locally:

```bash
planopticon auth google      # Google Drive, Docs, Meet, YouTube
planopticon auth dropbox     # Dropbox
planopticon auth zoom        # Zoom recordings
planopticon auth notion      # Notion pages
planopticon auth github      # GitHub repos and wikis
planopticon auth microsoft   # OneDrive, SharePoint, Teams
```

Credentials are stored in `~/.config/planopticon/`. Use `planopticon auth SERVICE --logout` to remove them.

For Zoom and Microsoft 365, you also need to set the client ID and secret environment variables before running `planopticon auth`.

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
