"""Dropbox source integration with OAuth support."""

import json
import logging
import os
import webbrowser
from pathlib import Path
from typing import List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)

# Video extensions we look for
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv"}

_TOKEN_PATH = Path.home() / ".planopticon" / "dropbox_token.json"


class DropboxSource(BaseSource):
    """
    Dropbox source with OAuth2 support.

    Auth methods:
    - Access token: Set DROPBOX_ACCESS_TOKEN env var for simple usage
    - OAuth2: Interactive browser-based flow with refresh tokens
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        token_path: Optional[Path] = None,
    ):
        """
        Initialize Dropbox source.

        Parameters
        ----------
        access_token : str, optional
            Direct access token. Falls back to DROPBOX_ACCESS_TOKEN env var.
        app_key : str, optional
            Dropbox app key for OAuth. Falls back to DROPBOX_APP_KEY env var.
        app_secret : str, optional
            Dropbox app secret for OAuth. Falls back to DROPBOX_APP_SECRET env var.
        token_path : Path, optional
            Where to store/load OAuth tokens.
        """
        self.access_token = access_token or os.environ.get("DROPBOX_ACCESS_TOKEN")
        self.app_key = app_key or os.environ.get("DROPBOX_APP_KEY")
        self.app_secret = app_secret or os.environ.get("DROPBOX_APP_SECRET")
        self.token_path = token_path or _TOKEN_PATH
        self.dbx = None

    def authenticate(self) -> bool:
        """Authenticate with Dropbox API."""
        try:
            import dropbox
        except ImportError:
            logger.error(
                "Dropbox SDK not installed. Run: pip install planopticon[dropbox]"
            )
            return False

        # Try direct access token first
        if self.access_token:
            return self._auth_token(dropbox)

        # Try saved OAuth token
        if self.token_path.exists():
            if self._auth_saved_token(dropbox):
                return True

        # Run OAuth flow
        return self._auth_oauth(dropbox)

    def _auth_token(self, dropbox) -> bool:
        """Authenticate with a direct access token."""
        try:
            self.dbx = dropbox.Dropbox(self.access_token)
            self.dbx.users_get_current_account()
            logger.info("Authenticated with Dropbox via access token")
            return True
        except Exception as e:
            logger.error(f"Dropbox access token auth failed: {e}")
            return False

    def _auth_saved_token(self, dropbox) -> bool:
        """Authenticate using a saved OAuth refresh token."""
        try:
            data = json.loads(self.token_path.read_text())
            refresh_token = data.get("refresh_token")
            app_key = data.get("app_key") or self.app_key
            app_secret = data.get("app_secret") or self.app_secret

            if not refresh_token or not app_key:
                return False

            self.dbx = dropbox.Dropbox(
                oauth2_refresh_token=refresh_token,
                app_key=app_key,
                app_secret=app_secret,
            )
            self.dbx.users_get_current_account()
            logger.info("Authenticated with Dropbox via saved token")
            return True
        except Exception:
            return False

    def _auth_oauth(self, dropbox) -> bool:
        """Run OAuth2 PKCE flow."""
        if not self.app_key:
            logger.error(
                "Dropbox app key not configured. Set DROPBOX_APP_KEY env var."
            )
            return False

        try:
            flow = dropbox.DropboxOAuth2FlowNoRedirect(
                consumer_key=self.app_key,
                consumer_secret=self.app_secret,
                token_access_type="offline",
                use_pkce=True,
            )

            authorize_url = flow.start()
            print(f"\nOpen this URL to authorize PlanOpticon:\n{authorize_url}\n")

            try:
                webbrowser.open(authorize_url)
            except Exception:
                pass

            auth_code = input("Enter the authorization code: ").strip()
            result = flow.finish(auth_code)

            self.dbx = dropbox.Dropbox(
                oauth2_refresh_token=result.refresh_token,
                app_key=self.app_key,
                app_secret=self.app_secret,
            )

            # Save token
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(
                json.dumps(
                    {
                        "refresh_token": result.refresh_token,
                        "app_key": self.app_key,
                        "app_secret": self.app_secret or "",
                    }
                )
            )
            logger.info(f"OAuth token saved to {self.token_path}")
            logger.info("Authenticated with Dropbox via OAuth")
            return True
        except Exception as e:
            logger.error(f"Dropbox OAuth failed: {e}")
            return False

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """List video files in a Dropbox folder."""
        if not self.dbx:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        path = folder_path or ""
        if path and not path.startswith("/"):
            path = f"/{path}"

        files = []
        try:
            result = self.dbx.files_list_folder(path, recursive=False)

            while True:
                for entry in result.entries:
                    import dropbox as dbx_module

                    if not isinstance(entry, dbx_module.files.FileMetadata):
                        continue

                    ext = Path(entry.name).suffix.lower()
                    if ext not in VIDEO_EXTENSIONS:
                        continue

                    if patterns:
                        if not any(
                            entry.name.endswith(p.replace("*", "")) for p in patterns
                        ):
                            continue

                    files.append(
                        SourceFile(
                            name=entry.name,
                            id=entry.id,
                            size_bytes=entry.size,
                            mime_type=None,
                            modified_at=entry.server_modified.isoformat()
                            if entry.server_modified
                            else None,
                            path=entry.path_display,
                        )
                    )

                if not result.has_more:
                    break
                result = self.dbx.files_list_folder_continue(result.cursor)

        except Exception as e:
            logger.error(f"Failed to list Dropbox folder: {e}")
            raise

        logger.info(f"Found {len(files)} videos in Dropbox")
        return files

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download a file from Dropbox."""
        if not self.dbx:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        path = file.path or f"/{file.name}"
        self.dbx.files_download_to_file(str(destination), path)

        logger.info(f"Downloaded {file.name} to {destination}")
        return destination
