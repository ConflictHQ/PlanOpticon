"""Markdown and plaintext document processors."""

import re
from pathlib import Path
from typing import List

from video_processor.processors.base import (
    DocumentChunk,
    DocumentProcessor,
    register_processor,
)


class MarkdownProcessor(DocumentProcessor):
    """Process Markdown files by splitting on headings."""

    supported_extensions = [".md", ".markdown"]

    def can_process(self, path: Path) -> bool:
        return path.suffix.lower() in self.supported_extensions

    def process(self, path: Path) -> List[DocumentChunk]:
        text = path.read_text(encoding="utf-8")
        source = str(path)

        # Split by headings (lines starting with # or ##)
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(heading_pattern.finditer(text))

        if not matches:
            # No headings — chunk by paragraphs
            return _chunk_by_paragraphs(text, source)

        chunks: List[DocumentChunk] = []

        # Content before the first heading
        if matches[0].start() > 0:
            preamble = text[: matches[0].start()].strip()
            if preamble:
                chunks.append(
                    DocumentChunk(
                        text=preamble,
                        source_file=source,
                        chunk_index=0,
                        section="(preamble)",
                    )
                )

        for i, match in enumerate(matches):
            section_title = match.group(2).strip()
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section_text = text[start:end].strip()

            if section_text:
                chunks.append(
                    DocumentChunk(
                        text=section_text,
                        source_file=source,
                        chunk_index=len(chunks),
                        section=section_title,
                    )
                )

        return chunks


class PlaintextProcessor(DocumentProcessor):
    """Process plaintext files by splitting on paragraph boundaries."""

    supported_extensions = [".txt", ".text", ".log", ".csv"]

    def can_process(self, path: Path) -> bool:
        return path.suffix.lower() in self.supported_extensions

    def process(self, path: Path) -> List[DocumentChunk]:
        text = path.read_text(encoding="utf-8")
        return _chunk_by_paragraphs(text, str(path))


def _chunk_by_paragraphs(
    text: str,
    source_file: str,
    max_chunk_size: int = 2000,
    overlap: int = 200,
) -> List[DocumentChunk]:
    """Split text into chunks by paragraph boundaries with configurable size and overlap."""
    # Split on double newlines (paragraph boundaries)
    paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if not paragraphs:
        return []

    chunks: List[DocumentChunk] = []
    current_text = ""

    for para in paragraphs:
        candidate = (current_text + "\n\n" + para).strip() if current_text else para

        if len(candidate) > max_chunk_size and current_text:
            # Flush current chunk
            chunks.append(
                DocumentChunk(
                    text=current_text,
                    source_file=source_file,
                    chunk_index=len(chunks),
                )
            )
            # Start next chunk with overlap from the end of current
            if overlap > 0 and len(current_text) > overlap:
                current_text = current_text[-overlap:] + "\n\n" + para
            else:
                current_text = para
        else:
            current_text = candidate

    # Flush remaining
    if current_text.strip():
        chunks.append(
            DocumentChunk(
                text=current_text.strip(),
                source_file=source_file,
                chunk_index=len(chunks),
            )
        )

    return chunks


# Register processors
register_processor(MarkdownProcessor.supported_extensions, MarkdownProcessor)
register_processor(PlaintextProcessor.supported_extensions, PlaintextProcessor)
