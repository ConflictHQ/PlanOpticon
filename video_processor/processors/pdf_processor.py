"""PDF document processor with graceful fallback between extraction libraries."""

from pathlib import Path
from typing import List

from video_processor.processors.base import (
    DocumentChunk,
    DocumentProcessor,
    register_processor,
)


class PdfProcessor(DocumentProcessor):
    """Process PDF files using pymupdf or pdfplumber."""

    supported_extensions = [".pdf"]

    def can_process(self, path: Path) -> bool:
        return path.suffix.lower() in self.supported_extensions

    def process(self, path: Path) -> List[DocumentChunk]:
        """Process a PDF, trying pymupdf first, then pdfplumber."""
        try:
            return self._process_pymupdf(path)
        except ImportError:
            pass

        try:
            return self._process_pdfplumber(path)
        except ImportError:
            raise ImportError(
                "PDF processing requires pymupdf or pdfplumber. "
                "Install with: pip install 'planopticon[pdf]'  OR  pip install pdfplumber"
            )

    def _process_pymupdf(self, path: Path) -> List[DocumentChunk]:
        import pymupdf

        doc = pymupdf.open(str(path))
        chunks: List[DocumentChunk] = []
        for page_num, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                chunks.append(
                    DocumentChunk(
                        text=text,
                        source_file=str(path),
                        chunk_index=page_num,
                        page=page_num + 1,
                        metadata={"extraction_method": "pymupdf"},
                    )
                )
        doc.close()
        return chunks

    def _process_pdfplumber(self, path: Path) -> List[DocumentChunk]:
        import pdfplumber

        chunks: List[DocumentChunk] = []
        with pdfplumber.open(str(path)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if text.strip():
                    chunks.append(
                        DocumentChunk(
                            text=text,
                            source_file=str(path),
                            chunk_index=page_num,
                            page=page_num + 1,
                            metadata={"extraction_method": "pdfplumber"},
                        )
                    )
        return chunks


# Register processor
register_processor(PdfProcessor.supported_extensions, PdfProcessor)
