"""Google Drive source integration with service account and OAuth support."""

import json
import logging
import os
from pathlib import Path
from typing import List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)

# Video MIME types we support
VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/x-matroska",
    "video/avi",
    "video/quicktime",
    "video/webm",
    "video/x-msvideo",
    "video/x-ms-wmv",
}

# Default OAuth scopes
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# OAuth client config for installed app flow
_DEFAULT_CLIENT_CONFIG = {
    "installed": {
        "client_id": os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""),
        "client_secret": os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

_TOKEN_PATH = Path.home() / ".planopticon" / "google_drive_token.json"


class GoogleDriveSource(BaseSource):
    """
    Google Drive source with dual auth support.

    Auth methods:
    - Service account: Set GOOGLE_APPLICATION_CREDENTIALS env var
    - OAuth2: Interactive browser-based flow for user accounts
    """

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        use_service_account: Optional[bool] = None,
        token_path: Optional[Path] = None,
    ):
        """
        Initialize Google Drive source.

        Parameters
        ----------
        credentials_path : str, optional
            Path to service account JSON or OAuth client secrets.
            Falls back to GOOGLE_APPLICATION_CREDENTIALS env var.
        use_service_account : bool, optional
            If True, force service account auth. If False, force OAuth.
            If None, auto-detect from credentials file.
        token_path : Path, optional
            Where to store/load OAuth tokens. Defaults to ~/.planopticon/google_drive_token.json
        """
        self.credentials_path = credentials_path or os.environ.get(
            "GOOGLE_APPLICATION_CREDENTIALS"
        )
        self.use_service_account = use_service_account
        self.token_path = token_path or _TOKEN_PATH
        self.service = None
        self._creds = None

    def authenticate(self) -> bool:
        """Authenticate with Google Drive API."""
        try:
            from google.oauth2 import service_account as sa_module
            from googleapiclient.discovery import build
        except ImportError:
            logger.error(
                "Google API client not installed. Run: pip install planopticon[gdrive]"
            )
            return False

        # Determine auth method
        if self.use_service_account is True or (
            self.use_service_account is None and self._is_service_account()
        ):
            return self._auth_service_account(build)
        else:
            return self._auth_oauth(build)

    def _is_service_account(self) -> bool:
        """Check if credentials file is a service account key."""
        if not self.credentials_path:
            return False
        try:
            with open(self.credentials_path) as f:
                data = json.load(f)
            return data.get("type") == "service_account"
        except Exception:
            return False

    def _auth_service_account(self, build) -> bool:
        """Authenticate using a service account."""
        try:
            from google.oauth2 import service_account as sa_module

            if not self.credentials_path:
                logger.error("No credentials path for service account auth")
                return False

            creds = sa_module.Credentials.from_service_account_file(
                self.credentials_path, scopes=SCOPES
            )
            self.service = build("drive", "v3", credentials=creds)
            self._creds = creds
            logger.info("Authenticated with Google Drive via service account")
            return True
        except Exception as e:
            logger.error(f"Service account auth failed: {e}")
            return False

    def _auth_oauth(self, build) -> bool:
        """Authenticate using OAuth2 installed app flow."""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:
            logger.error(
                "OAuth libraries not installed. Run: pip install planopticon[gdrive]"
            )
            return False

        creds = None

        # Load existing token
        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(self.token_path), SCOPES
                )
            except Exception:
                pass

        # Refresh or run new flow
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            client_config = _DEFAULT_CLIENT_CONFIG
            if self.credentials_path and Path(self.credentials_path).exists():
                try:
                    with open(self.credentials_path) as f:
                        client_config = json.load(f)
                except Exception:
                    pass

            if not client_config.get("installed", {}).get("client_id"):
                logger.error(
                    "OAuth client ID not configured. Set GOOGLE_OAUTH_CLIENT_ID "
                    "or provide a client secrets JSON file."
                )
                return False

            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)

            # Save token
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json())
            logger.info(f"OAuth token saved to {self.token_path}")

        self._creds = creds
        self.service = build("drive", "v3", credentials=creds)
        logger.info("Authenticated with Google Drive via OAuth")
        return True

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """List video files in a Google Drive folder."""
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        # Build query
        query_parts = []

        if folder_id:
            query_parts.append(f"'{folder_id}' in parents")

        # Filter for video MIME types
        mime_conditions = " or ".join(
            f"mimeType='{mt}'" for mt in VIDEO_MIME_TYPES
        )
        query_parts.append(f"({mime_conditions})")
        query_parts.append("trashed=false")

        query = " and ".join(query_parts)

        files = []
        page_token = None

        while True:
            response = (
                self.service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, size, mimeType, modifiedTime)",
                    pageToken=page_token,
                    pageSize=100,
                )
                .execute()
            )

            for f in response.get("files", []):
                # Apply pattern filtering if specified
                if patterns:
                    name = f.get("name", "")
                    if not any(
                        name.endswith(p.replace("*", "")) for p in patterns
                    ):
                        continue

                files.append(
                    SourceFile(
                        name=f["name"],
                        id=f["id"],
                        size_bytes=int(f.get("size", 0)) if f.get("size") else None,
                        mime_type=f.get("mimeType"),
                        modified_at=f.get("modifiedTime"),
                    )
                )

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        logger.info(f"Found {len(files)} videos in Google Drive")
        return files

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download a file from Google Drive."""
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        from googleapiclient.http import MediaIoBaseDownload
        import io

        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        request = self.service.files().get_media(fileId=file.id)
        with open(destination, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug(f"Download {file.name}: {int(status.progress() * 100)}%")

        logger.info(f"Downloaded {file.name} to {destination}")
        return destination
