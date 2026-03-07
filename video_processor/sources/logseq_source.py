"""Logseq graph source connector for ingesting markdown pages and journals."""

import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)


def parse_page(path: Path) -> dict:
    """Parse a Logseq markdown page and extract structured content.

    Returns a dict with:
        - properties: dict of page-level properties (key:: value lines at top)
        - links: list of linked page names from [[wiki-links]]
        - tags: list of tags from #tag and #[[tag]] occurrences
        - block_refs: list of block reference IDs from ((block-id))
        - body: full text content
    """
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")

    # Extract page properties (key:: value lines at the top of the file)
    properties: dict = {}
    body_start = 0
    for i, line in enumerate(lines):
        prop_match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*)::\ ?(.*)", line)
        if prop_match:
            key = prop_match.group(1)
            value = prop_match.group(2).strip()
            properties[key] = value
            body_start = i + 1
        else:
            break

    body = "\n".join(lines[body_start:])

    # Extract wiki-links: [[page]]
    link_pattern = re.compile(r"\[\[([^\]]+)\]\]")
    links = link_pattern.findall(body)
    # Also pick up links from properties
    for value in properties.values():
        links.extend(link_pattern.findall(str(value)))

    # Extract tags: #tag and #[[tag]]
    # First get #[[multi word tag]] style
    bracket_tag_pattern = re.compile(r"#\[\[([^\]]+)\]\]")
    tags = bracket_tag_pattern.findall(text)
    # Then get simple #tag style (exclude matches already captured as #[[...]])
    # Remove bracket tags first to avoid double-matching
    text_without_bracket_tags = bracket_tag_pattern.sub("", text)
    simple_tag_pattern = re.compile(r"(?<!\w)#([A-Za-z][A-Za-z0-9_/-]*)")
    tags.extend(simple_tag_pattern.findall(text_without_bracket_tags))

    # Extract block references: ((block-id))
    block_ref_pattern = re.compile(r"\(\(([a-f0-9-]+)\)\)")
    block_refs = block_ref_pattern.findall(text)

    return {
        "properties": properties,
        "links": links,
        "tags": tags,
        "block_refs": block_refs,
        "body": body,
    }


def ingest_graph(graph_path: Path) -> dict:
    """Ingest an entire Logseq graph and return structured data.

    Returns a dict with:
        - notes: list of dicts with name, tags, frontmatter (properties), text
        - links: list of (source, target) tuples from wiki-links
    """
    graph_path = Path(graph_path)
    notes: List[dict] = []
    links: List[Tuple[str, str]] = []

    md_files: List[Path] = []
    pages_dir = graph_path / "pages"
    journals_dir = graph_path / "journals"

    if pages_dir.is_dir():
        md_files.extend(sorted(pages_dir.rglob("*.md")))
    if journals_dir.is_dir():
        md_files.extend(sorted(journals_dir.rglob("*.md")))

    logger.info("Found %d markdown files in graph %s", len(md_files), graph_path)

    for md_file in md_files:
        page_name = md_file.stem
        try:
            parsed = parse_page(md_file)
        except Exception:
            logger.warning("Failed to parse page %s", md_file)
            continue

        notes.append(
            {
                "name": page_name,
                "tags": parsed["tags"],
                "frontmatter": parsed["properties"],
                "text": parsed["body"],
            }
        )

        for linked_page in parsed["links"]:
            links.append((page_name, linked_page))

    logger.info(
        "Ingested %d notes with %d links from graph %s",
        len(notes),
        len(links),
        graph_path,
    )
    return {"notes": notes, "links": links}


class LogseqSource(BaseSource):
    """Source connector for Logseq graphs."""

    def __init__(self, graph_path: str) -> None:
        self.graph_path = Path(graph_path)

    def authenticate(self) -> bool:
        """Check that the graph path exists and has pages/ or journals/ dirs."""
        if not self.graph_path.is_dir():
            logger.error("Graph path does not exist: %s", self.graph_path)
            return False
        has_pages = (self.graph_path / "pages").is_dir()
        has_journals = (self.graph_path / "journals").is_dir()
        if not has_pages and not has_journals:
            logger.error(
                "No pages/ or journals/ directory found in graph: %s",
                self.graph_path,
            )
            return False
        logger.info(
            "Logseq graph authenticated: %s (pages=%s, journals=%s)",
            self.graph_path,
            has_pages,
            has_journals,
        )
        return True

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """List .md files in pages/ and journals/ as SourceFile objects."""
        md_files: List[Path] = []

        pages_dir = self.graph_path / "pages"
        journals_dir = self.graph_path / "journals"

        if folder_path:
            search_root = self.graph_path / folder_path
            if search_root.is_dir():
                md_files.extend(sorted(search_root.rglob("*.md")))
        else:
            if pages_dir.is_dir():
                md_files.extend(sorted(pages_dir.rglob("*.md")))
            if journals_dir.is_dir():
                md_files.extend(sorted(journals_dir.rglob("*.md")))

        results: List[SourceFile] = []
        for md_file in md_files:
            relative = md_file.relative_to(self.graph_path)
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

        logger.info("Listed %d files from graph %s", len(results), self.graph_path)
        return results

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Copy a graph file to the destination path."""
        source = self.graph_path / file.id
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        logger.info("Copied %s -> %s", source, destination)
        return destination
