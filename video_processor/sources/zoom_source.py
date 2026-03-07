"""Zoom cloud recordings source integration with OAuth support."""

import base64
import hashlib
import json
import logging
import os
import secrets
import time
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional

import requests

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)

_TOKEN_PATH = Path.home() / ".planopticon" / "zoom_token.json"
_BASE_URL = "https://api.zoom.us/v2"
_OAUTH_BASE = "https://zoom.us/oauth"

# Map Zoom file_type values to MIME types
_MIME_TYPES = {
    "MP4": "video/mp4",
    "M4A": "audio/mp4",
    "CHAT": "text/plain",
    "TRANSCRIPT": "text/vtt",
    "CSV": "text/csv",
    "TIMELINE": "application/json",
}


class ZoomSource(BaseSource):
    """
    Zoom cloud recordings source with OAuth2 support.

    Auth methods (tried in order):
    1. Saved token: Load from token_path, refresh if expired
    2. Server-to-Server OAuth: Uses account_id with client credentials
    3. OAuth2 Authorization Code with PKCE: Interactive browser flow
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        account_id: Optional[str] = None,
        token_path: Optional[Path] = None,
    ):
        """
        Initialize Zoom source.

        Parameters
        ----------
        client_id : str, optional
            Zoom OAuth app client ID. Falls back to ZOOM_CLIENT_ID env var.
        client_secret : str, optional
            Zoom OAuth app client secret. Falls back to ZOOM_CLIENT_SECRET env var.
        account_id : str, optional
            Zoom account ID for Server-to-Server OAuth. Falls back to ZOOM_ACCOUNT_ID env var.
        token_path : Path, optional
            Where to store/load OAuth tokens.
        """
        self.client_id = client_id or os.environ.get("ZOOM_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("ZOOM_CLIENT_SECRET")
        self.account_id = account_id or os.environ.get("ZOOM_ACCOUNT_ID")
        self.token_path = token_path or _TOKEN_PATH
        self._access_token: Optional[str] = None
        self._token_data: Optional[Dict] = None

    def authenticate(self) -> bool:
        """Authenticate with Zoom API."""
        # Try 1: Load saved token
        if self.token_path.exists():
            if self._auth_saved_token():
                return True

        # Try 2: Server-to-Server OAuth (if account_id is set)
        if self.account_id:
            return self._auth_server_to_server()

        # Try 3: OAuth2 Authorization Code flow with PKCE
        return self._auth_oauth_pkce()

    def _auth_saved_token(self) -> bool:
        """Authenticate using a saved OAuth token, refreshing if expired."""
        try:
            data = json.loads(self.token_path.read_text())
            expires_at = data.get("expires_at", 0)

            if time.time() < expires_at:
                # Token still valid
                self._access_token = data["access_token"]
                self._token_data = data
                logger.info("Authenticated with Zoom via saved token")
                return True

            # Token expired, try to refresh
            if data.get("refresh_token"):
                return self._refresh_token()

            # Server-to-Server tokens don't have refresh tokens;
            # fall through to re-authenticate
            return False
        except Exception:
            return False

    def _auth_server_to_server(self) -> bool:
        """Authenticate using Server-to-Server OAuth (account credentials)."""
        if not self.client_id or not self.client_secret:
            logger.error(
                "Zoom client_id and client_secret required for Server-to-Server OAuth. "
                "Set ZOOM_CLIENT_ID and ZOOM_CLIENT_SECRET env vars."
            )
            return False

        try:
            resp = requests.post(
                f"{_OAUTH_BASE}/token",
                params={
                    "grant_type": "account_credentials",
                    "account_id": self.account_id,
                },
                auth=(self.client_id, self.client_secret),
                timeout=30,
            )
            resp.raise_for_status()
            token_data = resp.json()

            self._access_token = token_data["access_token"]
            self._token_data = {
                "access_token": token_data["access_token"],
                "expires_at": time.time() + token_data.get("expires_in", 3600) - 60,
                "token_type": token_data.get("token_type", "bearer"),
            }

            self._save_token(self._token_data)
            logger.info("Authenticated with Zoom via Server-to-Server OAuth")
            return True
        except Exception as e:
            logger.error(f"Zoom Server-to-Server OAuth failed: {e}")
            return False

    def _auth_oauth_pkce(self) -> bool:
        """Run OAuth2 Authorization Code flow with PKCE."""
        if not self.client_id:
            logger.error("Zoom client_id required for OAuth. Set ZOOM_CLIENT_ID env var.")
            return False

        try:
            # Generate PKCE code verifier and challenge
            code_verifier = secrets.token_urlsafe(64)
            code_challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest())
                .rstrip(b"=")
                .decode("ascii")
            )

            authorize_url = (
                f"{_OAUTH_BASE}/authorize"
                f"?response_type=code"
                f"&client_id={self.client_id}"
                f"&redirect_uri=urn:ietf:wg:oauth:2.0:oob"
                f"&code_challenge={code_challenge}"
                f"&code_challenge_method=S256"
            )

            print(f"\nOpen this URL to authorize PlanOpticon:\n{authorize_url}\n")

            try:
                webbrowser.open(authorize_url)
            except Exception:
                pass

            auth_code = input("Enter the authorization code: ").strip()

            # Exchange authorization code for tokens
            payload = {
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
                "code_verifier": code_verifier,
            }

            resp = requests.post(
                f"{_OAUTH_BASE}/token",
                data=payload,
                auth=(self.client_id, self.client_secret or ""),
                timeout=30,
            )
            resp.raise_for_status()
            token_data = resp.json()

            self._access_token = token_data["access_token"]
            self._token_data = {
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": time.time() + token_data.get("expires_in", 3600) - 60,
                "token_type": token_data.get("token_type", "bearer"),
                "client_id": self.client_id,
                "client_secret": self.client_secret or "",
            }

            self._save_token(self._token_data)
            logger.info("Authenticated with Zoom via OAuth PKCE")
            return True
        except Exception as e:
            logger.error(f"Zoom OAuth PKCE failed: {e}")
            return False

    def _refresh_token(self) -> bool:
        """Refresh an expired OAuth token."""
        try:
            data = json.loads(self.token_path.read_text())
            refresh_token = data.get("refresh_token")
            client_id = data.get("client_id") or self.client_id
            client_secret = data.get("client_secret") or self.client_secret

            if not refresh_token or not client_id:
                return False

            resp = requests.post(
                f"{_OAUTH_BASE}/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                auth=(client_id, client_secret or ""),
                timeout=30,
            )
            resp.raise_for_status()
            token_data = resp.json()

            self._access_token = token_data["access_token"]
            self._token_data = {
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token", refresh_token),
                "expires_at": time.time() + token_data.get("expires_in", 3600) - 60,
                "token_type": token_data.get("token_type", "bearer"),
                "client_id": client_id,
                "client_secret": client_secret or "",
            }

            self._save_token(self._token_data)
            logger.info("Refreshed Zoom OAuth token")
            return True
        except Exception as e:
            logger.error(f"Zoom token refresh failed: {e}")
            return False

    def _save_token(self, data: Dict) -> None:
        """Save token data to disk."""
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(json.dumps(data))
        logger.info(f"OAuth token saved to {self.token_path}")

    def _api_get(self, endpoint: str, params: Optional[Dict] = None) -> requests.Response:
        """Make an authenticated GET request to the Zoom API."""
        if not self._access_token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        url = f"{_BASE_URL}/{endpoint.lstrip('/')}"
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {self._access_token}"},
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """List video files from Zoom cloud recordings."""
        if not self._access_token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        files: List[SourceFile] = []
        next_page_token = ""

        while True:
            params: Dict = {}
            if next_page_token:
                params["next_page_token"] = next_page_token

            resp = self._api_get("users/me/recordings", params=params)
            data = resp.json()

            for meeting in data.get("meetings", []):
                meeting_id = str(meeting.get("id", ""))
                topic = meeting.get("topic", "Untitled Meeting")
                start_time = meeting.get("start_time")

                for rec_file in meeting.get("recording_files", []):
                    file_type = rec_file.get("file_type", "")
                    mime_type = _MIME_TYPES.get(file_type)

                    # Build a descriptive name
                    file_ext = rec_file.get("file_extension", file_type).lower()
                    file_name = f"{topic}.{file_ext}"

                    if patterns:
                        if not any(file_name.endswith(p.replace("*", "")) for p in patterns):
                            continue

                    files.append(
                        SourceFile(
                            name=file_name,
                            id=meeting_id,
                            size_bytes=rec_file.get("file_size"),
                            mime_type=mime_type,
                            modified_at=start_time,
                            path=rec_file.get("download_url"),
                        )
                    )

            next_page_token = data.get("next_page_token", "")
            if not next_page_token:
                break

        logger.info(f"Found {len(files)} recordings in Zoom")
        return files

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download a recording file from Zoom."""
        if not self._access_token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        download_url = file.path
        if not download_url:
            raise ValueError(f"No download URL for file: {file.name}")

        resp = requests.get(
            download_url,
            headers={"Authorization": f"Bearer {self._access_token}"},
            stream=True,
            timeout=60,
        )
        resp.raise_for_status()

        with open(destination, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"Downloaded {file.name} to {destination}")
        return destination

    def fetch_transcript(self, meeting_id: str) -> Optional[str]:
        """
        Fetch the transcript (VTT) for a Zoom meeting recording.

        Looks for transcript files in the recording's file list and downloads
        the content as text.

        Parameters
        ----------
        meeting_id : str
            The Zoom meeting ID.

        Returns
        -------
        str or None
            Transcript text if available, None otherwise.
        """
        if not self._access_token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        try:
            resp = self._api_get(f"meetings/{meeting_id}/recordings")
            data = resp.json()

            for rec_file in data.get("recording_files", []):
                file_type = rec_file.get("file_type", "")
                if file_type == "TRANSCRIPT":
                    download_url = rec_file.get("download_url")
                    if download_url:
                        dl_resp = requests.get(
                            download_url,
                            headers={"Authorization": f"Bearer {self._access_token}"},
                            timeout=30,
                        )
                        dl_resp.raise_for_status()
                        logger.info(f"Fetched transcript for meeting {meeting_id}")
                        return dl_resp.text

            logger.info(f"No transcript found for meeting {meeting_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch transcript for meeting {meeting_id}: {e}")
            return None
