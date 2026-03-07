"""Base classes and registry for document processors."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    """A chunk of text from a processed document."""

    text: str
    source_file: str
    chunk_index: int = 0
    page: Optional[int] = None
    section: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentProcessor(ABC):
    """Base class for document processors."""

    supported_extensions: List[str] = []

    @abstractmethod
    def process(self, path: Path) -> List[DocumentChunk]:
        """Process a document into chunks."""
        ...

    @abstractmethod
    def can_process(self, path: Path) -> bool:
        """Check if this processor can handle the file."""
        ...


# Registry
_processors: Dict[str, type] = {}


def register_processor(extensions: List[str], processor_class: type) -> None:
    """Register a processor class for the given file extensions."""
    for ext in extensions:
        _processors[ext.lower()] = processor_class


def get_processor(path: Path) -> Optional[DocumentProcessor]:
    """Get a processor instance for the given file path, or None if unsupported."""
    ext = path.suffix.lower()
    cls = _processors.get(ext)
    return cls() if cls else None


def list_supported_extensions() -> List[str]:
    """Return sorted list of all registered file extensions."""
    return sorted(_processors.keys())
