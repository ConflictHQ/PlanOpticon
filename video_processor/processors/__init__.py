"""Document processors for ingesting files into knowledge graphs."""

from video_processor.processors.base import (
    DocumentChunk,
    DocumentProcessor,
    get_processor,
    list_supported_extensions,
    register_processor,
)

__all__ = [
    "DocumentChunk",
    "DocumentProcessor",
    "get_processor",
    "list_supported_extensions",
    "register_processor",
]

# Auto-register built-in processors on import
from video_processor.processors import (
    markdown_processor,  # noqa: F401, E402
    pdf_processor,  # noqa: F401, E402
)
