"""GitHub source connector for fetching repo content, issues, and PRs."""

import logging
import os
from pathlib import Path
from typing import List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"


class GitHubSource(BaseSource):
    """
    Fetch GitHub repository README, issues, and pull requests as text documents.

    Auth: Set GITHUB_TOKEN env var, or use `gh auth token` output.
    Requires: pip install requests
    """

    def __init__(self, repo: str, include_issues: bool = True, include_prs: bool = True):
        """
        Parameters
        ----------
        repo : str
            GitHub repo in "owner/repo" format.
        """
        self.repo = repo
        self.include_issues = include_issues
        self.include_prs = include_prs
        self._token: Optional[str] = None

    def authenticate(self) -> bool:
        """Authenticate via GITHUB_TOKEN env var or gh CLI."""
        self._token = os.environ.get("GITHUB_TOKEN")
        if not self._token:
            try:
                import subprocess

                result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
                if result.returncode == 0:
                    self._token = result.stdout.strip()
            except FileNotFoundError:
                pass
        if not self._token:
            logger.warning(
                "No GitHub token found. Public repos only. Set GITHUB_TOKEN for private repos."
            )
        return True

    def _headers(self) -> dict:
        h = {"Accept": "application/vnd.github.v3+json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """List available documents (README, issues, PRs) as SourceFiles."""
        import requests

        files = []
        # README
        resp = requests.get(
            f"{API_BASE}/repos/{self.repo}/readme", headers=self._headers(), timeout=15
        )
        if resp.ok:
            files.append(SourceFile(name="README", id="readme", mime_type="text/markdown"))

        # Issues
        if self.include_issues:
            resp = requests.get(
                f"{API_BASE}/repos/{self.repo}/issues",
                headers=self._headers(),
                params={"state": "all", "per_page": 100},
                timeout=15,
            )
            if resp.ok:
                for issue in resp.json():
                    if "pull_request" not in issue:
                        files.append(
                            SourceFile(
                                name=f"Issue #{issue['number']}: {issue['title']}",
                                id=f"issue:{issue['number']}",
                                mime_type="text/plain",
                            )
                        )

        # PRs
        if self.include_prs:
            resp = requests.get(
                f"{API_BASE}/repos/{self.repo}/pulls",
                headers=self._headers(),
                params={"state": "all", "per_page": 100},
                timeout=15,
            )
            if resp.ok:
                for pr in resp.json():
                    files.append(
                        SourceFile(
                            name=f"PR #{pr['number']}: {pr['title']}",
                            id=f"pr:{pr['number']}",
                            mime_type="text/plain",
                        )
                    )

        return files

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download a single document (README, issue, or PR) as text."""
        import requests

        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        if file.id == "readme":
            resp = requests.get(
                f"{API_BASE}/repos/{self.repo}/readme",
                headers={**self._headers(), "Accept": "application/vnd.github.v3.raw"},
                timeout=15,
            )
            destination.write_text(resp.text, encoding="utf-8")
        elif file.id.startswith("issue:"):
            num = file.id.split(":")[1]
            resp = requests.get(
                f"{API_BASE}/repos/{self.repo}/issues/{num}",
                headers=self._headers(),
                timeout=15,
            )
            data = resp.json()
            text = f"# {data['title']}\n\n{data.get('body', '') or ''}"
            # Append comments
            comments_resp = requests.get(data["comments_url"], headers=self._headers(), timeout=15)
            if comments_resp.ok:
                for c in comments_resp.json():
                    text += f"\n\n---\n**{c['user']['login']}**: {c.get('body', '')}"
            destination.write_text(text, encoding="utf-8")
        elif file.id.startswith("pr:"):
            num = file.id.split(":")[1]
            resp = requests.get(
                f"{API_BASE}/repos/{self.repo}/pulls/{num}",
                headers=self._headers(),
                timeout=15,
            )
            data = resp.json()
            text = f"# PR: {data['title']}\n\n{data.get('body', '') or ''}"
            destination.write_text(text, encoding="utf-8")

        logger.info(f"Downloaded {file.name} to {destination}")
        return destination
