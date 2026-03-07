"""Obsidian vault source connector for ingesting markdown notes."""

import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)


def parse_note(path: Path) -> dict:
    """Parse an Obsidian markdown note and extract structured content.

    Returns a dict with:
        - frontmatter: dict of YAML frontmatter metadata
        - links: list of linked page names from [[wiki-links]]
        - tags: list of tags from #tag occurrences
        - headings: list of dicts with level and text
        - body: markdown text without frontmatter
    """
    text = path.read_text(encoding="utf-8")

    # Extract YAML frontmatter (simple key: value parser, stdlib only)
    frontmatter: dict = {}
    body = text
    fm_match = re.match(r"\A---\n(.*?\n)---\n?(.*)", text, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        for line in fm_text.strip().splitlines():
            kv = re.match(r"^([A-Za-z_][A-Za-z0-9_ -]*):\s*(.*)", line)
            if kv:
                key = kv.group(1).strip()
                value = kv.group(2).strip()
                # Strip surrounding quotes
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                # Handle YAML-style lists on a single line [a, b, c]
                list_match = re.match(r"^\[(.+)\]$", value)
                if list_match:
                    value = [v.strip().strip("\"'") for v in list_match.group(1).split(",")]
                frontmatter[key] = value
        body = fm_match.group(2)

    # Extract wiki-links: [[page]] and [[page|alias]]
    link_pattern = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
    links = link_pattern.findall(body)

    # Extract tags: #tag (but not inside code blocks or frontmatter)
    # Match #tag but not #[[tag]] (that's Logseq style) and not ## headings
    tag_pattern = re.compile(r"(?<!\w)#([A-Za-z][A-Za-z0-9_/-]*)")
    tags = tag_pattern.findall(body)

    # Extract headings hierarchy
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    headings = [
        {"level": len(m.group(1)), "text": m.group(2).strip()}
        for m in heading_pattern.finditer(body)
    ]

    return {
        "frontmatter": frontmatter,
        "links": links,
        "tags": tags,
        "headings": headings,
        "body": body,
    }


def ingest_vault(vault_path: Path) -> dict:
    """Ingest an entire Obsidian vault and return structured data.

    Returns a dict with:
        - notes: list of dicts with name, tags, frontmatter, text
        - links: list of (source, target) tuples from wiki-links
    """
    vault_path = Path(vault_path)
    notes: List[dict] = []
    links: List[Tuple[str, str]] = []

    md_files = sorted(vault_path.rglob("*.md"))
    logger.info("Found %d markdown files in vault %s", len(md_files), vault_path)

    for md_file in md_files:
        note_name = md_file.stem
        try:
            parsed = parse_note(md_file)
        except Exception:
            logger.warning("Failed to parse note %s", md_file)
            continue

        notes.append(
            {
                "name": note_name,
                "tags": parsed["tags"],
                "frontmatter": parsed["frontmatter"],
                "text": parsed["body"],
            }
        )

        for linked_page in parsed["links"]:
            links.append((note_name, linked_page))

    logger.info(
        "Ingested %d notes with %d links from vault %s",
        len(notes),
        len(links),
        vault_path,
    )
    return {"notes": notes, "links": links}


class ObsidianSource(BaseSource):
    """Source connector for Obsidian vaults."""

    def __init__(self, vault_path: str) -> None:
        self.vault_path = Path(vault_path)

    def authenticate(self) -> bool:
        """Check that the vault path exists and contains .md files."""
        if not self.vault_path.is_dir():
            logger.error("Vault path does not exist: %s", self.vault_path)
            return False
        md_files = list(self.vault_path.rglob("*.md"))
        if not md_files:
            logger.error("No markdown files found in vault: %s", self.vault_path)
            return False
        logger.info(
            "Obsidian vault authenticated: %s (%d .md files)",
            self.vault_path,
            len(md_files),
        )
        return True

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """List all .md files in the vault recursively as SourceFile objects."""
        search_root = self.vault_path
        if folder_path:
            search_root = self.vault_path / folder_path

        md_files = sorted(search_root.rglob("*.md"))
        results: List[SourceFile] = []

        for md_file in md_files:
            relative = md_file.relative_to(self.vault_path)
            stat = md_file.stat()
            modified_dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

            results.append(
                SourceFile(
                    name=md_file.name,
                    id=str(relative),
                    size_bytes=stat.st_size,
                    mime_type="text/markdown",
                    modified_at=modified_dt.isoformat(),
                    path=str(relative),
                )
            )

        logger.info("Listed %d files from vault %s", len(results), self.vault_path)
        return results

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Copy a vault file to the destination path."""
        source = self.vault_path / file.id
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        logger.info("Copied %s -> %s", source, destination)
        return destination
