# Cloud Sources

PlanOpticon connects to 20+ source platforms for fetching videos, documents, and notes.

## Google Drive

### Service account auth

For automated/server-side usage:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
planopticon batch --source gdrive --folder-id "abc123" -o ./output
```

### OAuth2 user auth

For interactive usage with your own Google account:

```bash
planopticon auth google
planopticon batch --source gdrive --folder-id "abc123" -o ./output
```

### Install

```bash
pip install planopticon[gdrive]
```

## Google Workspace (gws)

Full Google Workspace integration beyond just Drive. Access Docs, Sheets, Slides, and Meet recordings through the `gws` CLI group.

### Setup

```bash
planopticon auth google
```

A single Google OAuth session covers Drive, Docs, Sheets, Slides, and Meet.

### Usage

```bash
# List all Google Workspace content
planopticon gws list

# List only Google Docs
planopticon gws list --type docs

# List Meet recordings
planopticon gws list --type meet

# Fetch a specific file
planopticon gws fetch abc123def --output ./downloads

# Ingest an entire Drive folder into a knowledge base
planopticon gws ingest --folder-id abc123 --output ./kb --recursive
```

## Microsoft 365 (m365)

Access OneDrive, SharePoint, Teams recordings, and Outlook content.

### Setup

```bash
# Set your Azure AD app credentials
export MICROSOFT_CLIENT_ID="your-client-id"
export MICROSOFT_CLIENT_SECRET="your-client-secret"

# Authenticate
planopticon auth microsoft
```

### Usage

```bash
# List all Microsoft 365 content
planopticon m365 list

# List only Teams recordings
planopticon m365 list --type teams

# List SharePoint files from a specific site
planopticon m365 list --type sharepoint --site "Engineering"

# Fetch a specific file
planopticon m365 fetch item-id-123 --output ./downloads

# Ingest SharePoint content into a knowledge base
planopticon m365 ingest --site "Engineering" --path "/Shared Documents" --output ./kb --recursive
```

## Dropbox

### OAuth2 auth

```bash
planopticon auth dropbox
planopticon batch --source dropbox --folder "/Recordings" -o ./output
```

### Install

```bash
pip install planopticon[dropbox]
```

## YouTube

PlanOpticon can ingest YouTube videos by URL. Audio is extracted and transcribed, and any visible content (slides, diagrams) is captured from frames.

```bash
# Ingest a YouTube video
planopticon ingest "https://www.youtube.com/watch?v=example" --output ./kb

# Ingest a playlist
planopticon ingest "https://www.youtube.com/playlist?list=example" --output ./kb
```

YouTube ingestion uses `yt-dlp` under the hood. Install it separately if not already available:

```bash
pip install yt-dlp
```

## Meeting recordings

Access cloud recordings from Zoom, Microsoft Teams, and Google Meet.

### Zoom

```bash
# Set credentials and authenticate
export ZOOM_CLIENT_ID="your-client-id"
export ZOOM_CLIENT_SECRET="your-client-secret"
planopticon auth zoom

# List recent Zoom recordings
planopticon recordings zoom-list

# List recordings from a date range
planopticon recordings zoom-list --from 2026-01-01 --to 2026-02-01
```

### Microsoft Teams

```bash
# Authenticate with Microsoft (covers Teams)
planopticon auth microsoft

# List Teams recordings
planopticon recordings teams-list

# List recordings from a date range
planopticon recordings teams-list --from 2026-01-01 --to 2026-02-01
```

### Google Meet

```bash
# Authenticate with Google (covers Meet)
planopticon auth google

# List Meet recordings
planopticon recordings meet-list --limit 10
```

## Notes sources

PlanOpticon can ingest notes and documents from several note-taking platforms.

### Obsidian

Ingest an Obsidian vault directly. PlanOpticon follows wikilinks and parses frontmatter.

```bash
planopticon ingest ~/Obsidian/MyVault --output ./kb --recursive
```

### Notion

```bash
# Set your Notion integration token
export NOTION_API_KEY="secret_..."

# Authenticate
planopticon auth notion

# Export knowledge base to Notion
planopticon export notion --input ./kb --parent-page abc123
```

### Apple Notes

PlanOpticon can read Apple Notes on macOS via the system AppleScript bridge.

```bash
planopticon ingest --source apple-notes --output ./kb
```

### GitHub

Ingest README files, wikis, and documentation from GitHub repositories.

```bash
# Set your GitHub token
export GITHUB_TOKEN="ghp_..."

# Authenticate
planopticon auth github

# Ingest a repo's docs
planopticon ingest "github://ConflictHQ/PlanOpticon" --output ./kb
```

## All cloud sources

```bash
pip install planopticon[cloud]
```
