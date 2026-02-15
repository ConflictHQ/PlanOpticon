"""Base interface for cloud source integrations."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SourceFile(BaseModel):
    """A file available in a cloud source."""
    name: str = Field(description="File name")
    id: str = Field(description="Provider-specific file identifier")
    size_bytes: Optional[int] = Field(default=None, description="File size in bytes")
    mime_type: Optional[str] = Field(default=None, description="MIME type")
    modified_at: Optional[str] = Field(default=None, description="Last modified timestamp")
    path: Optional[str] = Field(default=None, description="Path within the source folder")


class BaseSource(ABC):
    """Abstract base class for cloud source integrations."""

    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the cloud provider. Returns True on success."""
        ...

    @abstractmethod
    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """List video files in a folder."""
        ...

    @abstractmethod
    def download(
        self,
        file: SourceFile,
        destination: Path,
    ) -> Path:
        """Download a file to a local path. Returns the local path."""
        ...

    def download_all(
        self,
        files: List[SourceFile],
        destination_dir: Path,
    ) -> List[Path]:
        """Download multiple files to a directory, preserving subfolder structure."""
        destination_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for f in files:
            # Use path (with subfolder) if available, otherwise just name
            relative = f.path if f.path else f.name
            dest = destination_dir / relative
            try:
                local_path = self.download(f, dest)
                paths.append(local_path)
                logger.info(f"Downloaded: {relative}")
            except Exception as e:
                logger.error(f"Failed to download {relative}: {e}")
        return paths
