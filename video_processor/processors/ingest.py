"""Document ingestion — process files and add content to a knowledge graph."""

import hashlib
import logging
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from video_processor.integrators.knowledge_graph import KnowledgeGraph
from video_processor.processors.base import get_processor, list_supported_extensions

logger = logging.getLogger(__name__)


def ingest_file(
    path: Path,
    knowledge_graph: KnowledgeGraph,
    source_id: Optional[str] = None,
) -> int:
    """Process a single file and add its content to the knowledge graph.

    Returns the number of chunks processed.
    """
    processor = get_processor(path)
    if processor is None:
        raise ValueError(
            f"No processor for {path.suffix}. Supported: {', '.join(list_supported_extensions())}"
        )

    chunks = processor.process(path)

    if source_id is None:
        source_id = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:12]

    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    knowledge_graph.register_source(
        {
            "source_id": source_id,
            "source_type": "document",
            "title": path.stem,
            "path": str(path),
            "mime_type": mime,
            "ingested_at": datetime.now().isoformat(),
            "metadata": {"chunks": len(chunks), "extension": path.suffix},
        }
    )

    for chunk in chunks:
        content_source = f"document:{path.name}"
        if chunk.page is not None:
            content_source += f":page:{chunk.page}"
        elif chunk.section:
            content_source += f":section:{chunk.section}"
        knowledge_graph.add_content(chunk.text, content_source)

    return len(chunks)


def ingest_directory(
    directory: Path,
    knowledge_graph: KnowledgeGraph,
    recursive: bool = True,
    extensions: Optional[List[str]] = None,
) -> Dict[str, int]:
    """Process all supported files in a directory.

    Returns a dict mapping filename to chunk count.
    """
    if not directory.is_dir():
        raise ValueError(f"Not a directory: {directory}")

    supported = set(extensions) if extensions else set(list_supported_extensions())
    results: Dict[str, int] = {}

    glob_fn = directory.rglob if recursive else directory.glob
    files = sorted(f for f in glob_fn("*") if f.is_file() and f.suffix.lower() in supported)

    for file_path in files:
        try:
            count = ingest_file(file_path, knowledge_graph)
            results[str(file_path)] = count
            logger.info(f"Ingested {file_path.name}: {count} chunks")
        except Exception as e:
            logger.warning(f"Failed to ingest {file_path.name}: {e}")
            results[str(file_path)] = 0

    return results
