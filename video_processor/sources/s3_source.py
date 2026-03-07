"""AWS S3 source connector for fetching videos from S3 buckets."""

import logging
from pathlib import Path
from typing import List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".flv", ".wmv"}


class S3Source(BaseSource):
    """Fetches videos from an S3 bucket. Requires boto3 (optional dependency)."""

    def __init__(self, bucket: str, prefix: str = "", region: Optional[str] = None):
        self.bucket = bucket
        self.prefix = prefix
        self.region = region
        self._client = None

    def authenticate(self) -> bool:
        """Check for AWS credentials by initializing an S3 client."""
        try:
            import boto3
        except ImportError:
            logger.error("boto3 is not installed. Install with: pip install boto3")
            return False
        try:
            kwargs = {}
            if self.region:
                kwargs["region_name"] = self.region
            self._client = boto3.client("s3", **kwargs)
            self._client.head_bucket(Bucket=self.bucket)
            return True
        except Exception as e:
            logger.error(f"S3 authentication failed: {e}")
            return False

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """List video files in the bucket under the configured prefix."""
        if not self._client:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        prefix = folder_path or self.prefix
        paginator = self._client.get_paginator("list_objects_v2")
        files: List[SourceFile] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                suffix = Path(key).suffix.lower()
                if suffix in _VIDEO_EXTENSIONS:
                    files.append(
                        SourceFile(
                            name=Path(key).name,
                            id=key,
                            size_bytes=obj.get("Size"),
                            modified_at=str(obj.get("LastModified", "")),
                            path=key,
                        )
                    )
        return files

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download a single file from S3 to a local path."""
        if not self._client:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(self.bucket, file.id, str(destination))
        logger.info(f"Downloaded s3://{self.bucket}/{file.id} -> {destination}")
        return destination
