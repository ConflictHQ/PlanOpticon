"""Google Workspace source connector using the gws CLI (googleworkspace/cli).

Fetches and collates Google Docs, Sheets, Slides, and other Drive files
via the `gws` CLI tool. Outputs plain text suitable for KG ingestion.

Requires: npm install -g @googleworkspace/cli
Auth:     gws auth login (interactive) or GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE (headless)
"""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)

# Google Workspace MIME types we can extract text from
_DOC_MIMES = {
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.presentation",
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/html",
}

# Export MIME mappings for native Google formats
_EXPORT_MIMES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


def _run_gws(args: List[str], timeout: int = 30) -> Dict[str, Any]:
    """Run a gws CLI command and return parsed JSON output."""
    cmd = ["gws"] + args
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"gws {' '.join(args)} failed: {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"raw": proc.stdout.strip()}


class GWSSource(BaseSource):
    """
    Fetch documents from Google Workspace (Drive, Docs, Sheets, Slides) via gws CLI.

    Usage:
        source = GWSSource(folder_id="1abc...")   # specific Drive folder
        source = GWSSource(query="type:document")  # Drive search query
        files = source.list_videos()               # lists docs, not just videos
        source.download_all(files, Path("./docs"))
    """

    def __init__(
        self,
        folder_id: Optional[str] = None,
        query: Optional[str] = None,
        doc_ids: Optional[List[str]] = None,
        mime_filter: Optional[List[str]] = None,
    ):
        self.folder_id = folder_id
        self.query = query
        self.doc_ids = doc_ids or []
        self.mime_filter = set(mime_filter) if mime_filter else _DOC_MIMES

    def authenticate(self) -> bool:
        """Check if gws CLI is installed and authenticated."""
        if not shutil.which("gws"):
            logger.error("gws CLI not found. Install with: npm install -g @googleworkspace/cli")
            return False
        try:
            _run_gws(["auth", "status"], timeout=10)
            return True
        except (RuntimeError, subprocess.TimeoutExpired):
            logger.error("gws not authenticated. Run: gws auth login")
            return False

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """List documents in Drive. Despite the method name, returns docs not just videos."""
        folder = folder_id or self.folder_id
        files: List[SourceFile] = []

        # If specific doc IDs were provided, fetch metadata for each
        if self.doc_ids:
            for doc_id in self.doc_ids:
                try:
                    result = _run_gws(
                        [
                            "drive",
                            "files",
                            "get",
                            "--params",
                            json.dumps(
                                {"fileId": doc_id, "fields": "id,name,mimeType,size,modifiedTime"}
                            ),
                        ]
                    )
                    files.append(_result_to_source_file(result))
                except RuntimeError as e:
                    logger.warning(f"Failed to fetch doc {doc_id}: {e}")
            return files

        # Build Drive files list query
        params: Dict[str, Any] = {
            "pageSize": 100,
            "fields": "files(id,name,mimeType,size,modifiedTime)",
        }

        q_parts = []
        if folder:
            q_parts.append(f"'{folder}' in parents")
        if self.query:
            q_parts.append(self.query)
        # Filter to document types
        mime_clauses = [f"mimeType='{m}'" for m in self.mime_filter]
        if mime_clauses:
            q_parts.append(f"({' or '.join(mime_clauses)})")
        if q_parts:
            params["q"] = " and ".join(q_parts)

        try:
            result = _run_gws(
                [
                    "drive",
                    "files",
                    "list",
                    "--params",
                    json.dumps(params),
                ],
                timeout=60,
            )
        except RuntimeError as e:
            logger.error(f"Failed to list Drive files: {e}")
            return []

        for item in result.get("files", []):
            files.append(_result_to_source_file(item))

        logger.info(f"Found {len(files)} document(s) in Google Drive")
        return files

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download/export a document to a local text file."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        mime = file.mime_type or ""

        # Native Google format — export as text
        if mime in _EXPORT_MIMES:
            content = self._export_doc(file.id, mime)
        # Regular file — download directly
        else:
            content = self._download_file(file.id)

        destination.write_text(content, encoding="utf-8")
        logger.info(f"Saved {file.name} to {destination}")
        return destination

    def _export_doc(self, file_id: str, source_mime: str) -> str:
        """Export a native Google doc to text via gws."""
        export_mime = _EXPORT_MIMES.get(source_mime, "text/plain")
        try:
            result = _run_gws(
                [
                    "drive",
                    "files",
                    "export",
                    "--params",
                    json.dumps({"fileId": file_id, "mimeType": export_mime}),
                ],
                timeout=60,
            )
            return result.get("raw", json.dumps(result, indent=2))
        except RuntimeError:
            # Fallback: try getting via Docs API for Google Docs
            if source_mime == "application/vnd.google-apps.document":
                return self._get_doc_text(file_id)
            raise

    def _get_doc_text(self, doc_id: str) -> str:
        """Fetch Google Doc content via the Docs API and extract text."""
        result = _run_gws(
            [
                "docs",
                "documents",
                "get",
                "--params",
                json.dumps({"documentId": doc_id}),
            ],
            timeout=60,
        )

        # Extract text from the Docs API structural response
        body = result.get("body", {})
        content_parts = []
        for element in body.get("content", []):
            paragraph = element.get("paragraph", {})
            for pe in paragraph.get("elements", []):
                text_run = pe.get("textRun", {})
                text = text_run.get("content", "")
                if text.strip():
                    content_parts.append(text)

        return "".join(content_parts) if content_parts else json.dumps(result, indent=2)

    def _download_file(self, file_id: str) -> str:
        """Download a non-native file's content."""
        result = _run_gws(
            [
                "drive",
                "files",
                "get",
                "--params",
                json.dumps({"fileId": file_id, "alt": "media"}),
            ],
            timeout=60,
        )
        return result.get("raw", json.dumps(result, indent=2))

    def fetch_all_text(self, folder_id: Optional[str] = None) -> Dict[str, str]:
        """Convenience: list all docs and return {filename: text_content} dict."""
        files = self.list_videos(folder_id=folder_id)
        results = {}
        for f in files:
            try:
                if f.mime_type and f.mime_type in _EXPORT_MIMES:
                    results[f.name] = self._export_doc(f.id, f.mime_type)
                else:
                    results[f.name] = self._download_file(f.id)
            except Exception as e:
                logger.warning(f"Failed to fetch {f.name}: {e}")
                results[f.name] = f"[Error: {e}]"
        return results

    def collate(self, folder_id: Optional[str] = None, separator: str = "\n\n---\n\n") -> str:
        """Fetch all docs and collate into a single text blob for ingestion."""
        docs = self.fetch_all_text(folder_id=folder_id)
        parts = []
        for name, content in docs.items():
            parts.append(f"# {name}\n\n{content}")
        return separator.join(parts)


def _result_to_source_file(item: dict) -> SourceFile:
    """Convert a Drive API file result to SourceFile."""
    size = item.get("size")
    return SourceFile(
        name=item.get("name", "Untitled"),
        id=item.get("id", ""),
        size_bytes=int(size) if size else None,
        mime_type=item.get("mimeType"),
        modified_at=item.get("modifiedTime"),
    )
