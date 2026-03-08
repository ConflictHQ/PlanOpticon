# Sources API Reference

::: video_processor.sources.base

---

## Overview

The sources module provides a unified interface for fetching content from cloud services, local applications, and the web. All sources implement the `BaseSource` abstract class, providing consistent `authenticate()`, `list_videos()`, and `download()` methods.

Sources are lazy-loaded to avoid pulling in optional dependencies at import time. You can import any source directly from `video_processor.sources` and the correct module will be loaded on demand.

---

## BaseSource (ABC)

```python
from video_processor.sources import BaseSource
```

Abstract base class that all source integrations implement. Defines the standard three-step workflow: authenticate, list, download.

### authenticate()

```python
@abstractmethod
def authenticate(self) -> bool
```

Authenticate with the cloud provider or service. Uses the auth strategy defined for the source (OAuth, API key, local access, etc.).

**Returns:** `bool` -- `True` on successful authentication, `False` on failure.

### list_videos()

```python
@abstractmethod
def list_videos(
    self,
    folder_id: Optional[str] = None,
    folder_path: Optional[str] = None,
    patterns: Optional[List[str]] = None,
) -> List[SourceFile]
```

List available video files (or other content, depending on the source).

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `folder_id` | `Optional[str]` | `None` | Provider-specific folder/container identifier |
| `folder_path` | `Optional[str]` | `None` | Path within the source (e.g., folder name) |
| `patterns` | `Optional[List[str]]` | `None` | File name glob patterns to filter results |

**Returns:** `List[SourceFile]` -- available files matching the criteria.

### download()

```python
@abstractmethod
def download(
    self,
    file: SourceFile,
    destination: Path,
) -> Path
```

Download a single file to a local path.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `file` | `SourceFile` | File descriptor from `list_videos()` |
| `destination` | `Path` | Local destination path |

**Returns:** `Path` -- the local path where the file was saved.

### download_all()

```python
def download_all(
    self,
    files: List[SourceFile],
    destination_dir: Path,
) -> List[Path]
```

Download multiple files to a directory, preserving subfolder structure from `SourceFile.path`. This is a concrete method provided by the base class.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `files` | `List[SourceFile]` | Files to download |
| `destination_dir` | `Path` | Base directory for downloads (created if needed) |

**Returns:** `List[Path]` -- local paths of successfully downloaded files. Failed downloads are logged and skipped.

---

## SourceFile

```python
from video_processor.sources import SourceFile
```

Pydantic model describing a file available in a cloud source.

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | *required* | File name |
| `id` | `str` | *required* | Provider-specific file identifier |
| `size_bytes` | `Optional[int]` | `None` | File size in bytes |
| `mime_type` | `Optional[str]` | `None` | MIME type (e.g., `"video/mp4"`) |
| `modified_at` | `Optional[str]` | `None` | Last modified timestamp |
| `path` | `Optional[str]` | `None` | Path within the source folder (used for subfolder structure in `download_all`) |

```json
{
  "name": "sprint-review-2026-03-01.mp4",
  "id": "abc123def456",
  "size_bytes": 524288000,
  "mime_type": "video/mp4",
  "modified_at": "2026-03-01T14:30:00Z",
  "path": "recordings/march/sprint-review-2026-03-01.mp4"
}
```

---

## Lazy Loading Pattern

All sources are lazy-loaded via `__getattr__` in the package `__init__.py`. This means importing `video_processor.sources` does not pull in any external dependencies (e.g., `google-auth`, `msal`, `notion-client`). The actual module is loaded only when you access the class.

```python
# This import is instant -- no dependencies loaded
from video_processor.sources import ZoomSource

# The zoom_source module (and its dependencies) are loaded here
source = ZoomSource()
```

---

## Available Sources

### Cloud Recordings

Sources for fetching recorded meetings from video conferencing platforms.

| Source | Class | Auth Method | Description |
|---|---|---|---|
| Zoom | `ZoomSource` | OAuth / Server-to-Server | List and download Zoom cloud recordings |
| Google Meet | `MeetRecordingSource` | OAuth (Google) | List and download Google Meet recordings from Drive |
| Microsoft Teams | `TeamsRecordingSource` | OAuth (Microsoft) | List and download Teams meeting recordings |

### Cloud Storage and Workspace

Sources for accessing files stored in cloud platforms.

| Source | Class | Auth Method | Description |
|---|---|---|---|
| Google Drive | `GoogleDriveSource` | OAuth (Google) | Files from Google Drive |
| Google Workspace | `GWSSource` | OAuth (Google) | Google Docs, Sheets, Slides |
| Microsoft 365 | `M365Source` | OAuth (Microsoft) | OneDrive, SharePoint files |
| Notion | `NotionSource` | OAuth / API key | Notion pages and databases |
| GitHub | `GitHubSource` | OAuth / API token | Repository files, issues, discussions |
| Dropbox | `DropboxSource` | OAuth / access token | *(via auth config)* |

### Notes Applications

Sources for local and cloud-based note-taking apps.

| Source | Class | Auth Method | Description |
|---|---|---|---|
| Apple Notes | `AppleNotesSource` | Local (macOS) | Notes from Apple Notes.app |
| Obsidian | `ObsidianSource` | Local filesystem | Markdown files from Obsidian vaults |
| Logseq | `LogseqSource` | Local filesystem | Pages from Logseq graphs |
| OneNote | `OneNoteSource` | OAuth (Microsoft) | Microsoft OneNote notebooks |
| Google Keep | `GoogleKeepSource` | OAuth (Google) | Google Keep notes |

### Web and Content

Sources for fetching content from the web.

| Source | Class | Auth Method | Description |
|---|---|---|---|
| YouTube | `YouTubeSource` | API key / OAuth | YouTube video metadata and transcripts |
| Web | `WebSource` | None | General web page content extraction |
| RSS | `RSSSource` | None | RSS/Atom feed entries |
| Podcast | `PodcastSource` | None | Podcast episodes from RSS feeds |
| arXiv | `ArxivSource` | None | Academic papers from arXiv |
| Hacker News | `HackerNewsSource` | None | Hacker News posts and comments |
| Reddit | `RedditSource` | API credentials | Reddit posts and comments |
| Twitter/X | `TwitterSource` | API credentials | Tweets and threads |

---

## Auth Integration

Most sources use PlanOpticon's unified auth system (see [Auth API](auth.md)). The typical pattern within a source implementation:

```python
from video_processor.auth import get_auth_manager

class MySource(BaseSource):
    def __init__(self):
        self._token = None

    def authenticate(self) -> bool:
        manager = get_auth_manager("my_service")
        if manager:
            token = manager.get_token()
            if token:
                self._token = token
                return True
        return False

    def list_videos(self, **kwargs) -> list[SourceFile]:
        if not self._token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        # Use self._token to call the API
        ...
```

---

## Usage Examples

### Listing and downloading Zoom recordings

```python
from pathlib import Path
from video_processor.sources import ZoomSource

source = ZoomSource()
if source.authenticate():
    recordings = source.list_videos()
    for rec in recordings:
        print(f"{rec.name} ({rec.size_bytes} bytes)")

    # Download all to a local directory
    paths = source.download_all(recordings, Path("./downloads"))
```

### Fetching from multiple sources

```python
from pathlib import Path
from video_processor.sources import GoogleDriveSource, NotionSource

# Google Drive
gdrive = GoogleDriveSource()
if gdrive.authenticate():
    files = gdrive.list_videos(
        folder_path="Meeting Recordings",
        patterns=["*.mp4", "*.webm"],
    )
    gdrive.download_all(files, Path("./drive-downloads"))

# Notion
notion = NotionSource()
if notion.authenticate():
    pages = notion.list_videos()  # Lists Notion pages
    for page in pages:
        print(f"Page: {page.name}")
```

### YouTube content

```python
from video_processor.sources import YouTubeSource

yt = YouTubeSource()
if yt.authenticate():
    videos = yt.list_videos(folder_path="https://youtube.com/playlist?list=...")
    for v in videos:
        print(f"{v.name} - {v.id}")
```
