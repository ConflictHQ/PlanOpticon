"""Tests for document processors and ingestion pipeline."""

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from video_processor.processors.base import (
    DocumentChunk,
    DocumentProcessor,
    get_processor,
    list_supported_extensions,
    register_processor,
)
from video_processor.processors.markdown_processor import (
    MarkdownProcessor,
    PlaintextProcessor,
    _chunk_by_paragraphs,
)
from video_processor.processors.pdf_processor import PdfProcessor

# --- Base / Registry ---


class TestRegistry:
    def test_list_supported_extensions_includes_builtins(self):
        exts = list_supported_extensions()
        assert ".md" in exts
        assert ".txt" in exts
        assert ".pdf" in exts

    def test_get_processor_markdown(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("hello")
        proc = get_processor(f)
        assert isinstance(proc, MarkdownProcessor)

    def test_get_processor_txt(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("hello")
        proc = get_processor(f)
        assert isinstance(proc, PlaintextProcessor)

    def test_get_processor_pdf(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_text("")
        proc = get_processor(f)
        assert isinstance(proc, PdfProcessor)

    def test_get_processor_unknown(self, tmp_path):
        f = tmp_path / "doc.xyz"
        f.write_text("")
        assert get_processor(f) is None

    def test_register_custom_processor(self, tmp_path):
        class CustomProcessor(DocumentProcessor):
            supported_extensions = [".custom"]

            def can_process(self, path):
                return path.suffix == ".custom"

            def process(self, path):
                return [DocumentChunk(text="custom", source_file=str(path), chunk_index=0)]

        register_processor([".custom"], CustomProcessor)
        f = tmp_path / "test.custom"
        f.write_text("data")
        proc = get_processor(f)
        assert isinstance(proc, CustomProcessor)
        chunks = proc.process(f)
        assert len(chunks) == 1
        assert chunks[0].text == "custom"


# --- Markdown ---


class TestMarkdownProcessor:
    def test_splits_by_headings(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text(
            textwrap.dedent("""\
            # Introduction
            Some intro text.

            ## Details
            More details here.

            ## Conclusion
            Final thoughts.
            """)
        )
        proc = MarkdownProcessor()
        assert proc.can_process(md)
        chunks = proc.process(md)

        assert len(chunks) == 3
        assert chunks[0].section == "Introduction"
        assert "intro text" in chunks[0].text
        assert chunks[1].section == "Details"
        assert chunks[2].section == "Conclusion"

    def test_preamble_before_first_heading(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text(
            textwrap.dedent("""\
            Some preamble text.

            # First Heading
            Content here.
            """)
        )
        proc = MarkdownProcessor()
        chunks = proc.process(md)
        assert len(chunks) == 2
        assert chunks[0].section == "(preamble)"
        assert "preamble" in chunks[0].text

    def test_no_headings_falls_back_to_paragraphs(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("Paragraph one.\n\nParagraph two.\n\nParagraph three.")
        proc = MarkdownProcessor()
        chunks = proc.process(md)
        assert len(chunks) >= 1
        # All text should be captured
        full_text = " ".join(c.text for c in chunks)
        assert "Paragraph one" in full_text
        assert "Paragraph three" in full_text

    def test_chunk_index_increments(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("# A\ntext\n# B\ntext\n# C\ntext")
        proc = MarkdownProcessor()
        chunks = proc.process(md)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_source_file_set(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("# Heading\nContent")
        proc = MarkdownProcessor()
        chunks = proc.process(md)
        assert chunks[0].source_file == str(md)


# --- Plaintext ---


class TestPlaintextProcessor:
    def test_basic_paragraphs(self, tmp_path):
        txt = tmp_path / "test.txt"
        txt.write_text("First paragraph.\n\nSecond paragraph.\n\nThird paragraph.")
        proc = PlaintextProcessor()
        assert proc.can_process(txt)
        chunks = proc.process(txt)
        assert len(chunks) >= 1
        full_text = " ".join(c.text for c in chunks)
        assert "First paragraph" in full_text
        assert "Third paragraph" in full_text

    def test_handles_log_files(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text("line 1\nline 2\nline 3")
        proc = PlaintextProcessor()
        assert proc.can_process(log)
        chunks = proc.process(log)
        assert len(chunks) >= 1

    def test_handles_csv(self, tmp_path):
        csv = tmp_path / "data.csv"
        csv.write_text("a,b,c\n1,2,3\n4,5,6")
        proc = PlaintextProcessor()
        assert proc.can_process(csv)
        chunks = proc.process(csv)
        assert len(chunks) >= 1

    def test_empty_file(self, tmp_path):
        txt = tmp_path / "empty.txt"
        txt.write_text("")
        proc = PlaintextProcessor()
        chunks = proc.process(txt)
        assert chunks == []


class TestChunkByParagraphs:
    def test_respects_max_chunk_size(self):
        # Create text with many paragraphs that exceed max size
        paragraphs = ["A" * 500 for _ in range(10)]
        text = "\n\n".join(paragraphs)
        chunks = _chunk_by_paragraphs(text, "test.txt", max_chunk_size=1200, overlap=100)
        assert len(chunks) > 1
        for chunk in chunks:
            # Each chunk should be reasonably sized (allowing for overlap)
            assert len(chunk.text) < 2000

    def test_overlap(self):
        text = "Para A " * 300 + "\n\n" + "Para B " * 300 + "\n\n" + "Para C " * 300
        chunks = _chunk_by_paragraphs(text, "test.txt", max_chunk_size=2500, overlap=200)
        if len(chunks) > 1:
            # The second chunk should contain some overlap from the first
            assert len(chunks[1].text) > 200


# --- PDF ---


class TestPdfProcessor:
    def test_can_process(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_text("")
        proc = PdfProcessor()
        assert proc.can_process(f)
        assert not proc.can_process(tmp_path / "doc.txt")

    def test_process_pymupdf(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_text("")

        mock_page = MagicMock()
        mock_page.get_text.return_value = "Page 1 content"
        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)

        mock_pymupdf = MagicMock()
        mock_pymupdf.open.return_value = mock_doc

        with patch.dict("sys.modules", {"pymupdf": mock_pymupdf}):
            proc = PdfProcessor()
            chunks = proc._process_pymupdf(f)
            assert len(chunks) == 1
            assert chunks[0].text == "Page 1 content"
            assert chunks[0].page == 1
            assert chunks[0].metadata["extraction_method"] == "pymupdf"

    def test_process_pdfplumber(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_text("")

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page 1 via pdfplumber"
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        mock_pdfplumber = MagicMock()
        mock_pdfplumber.open.return_value = mock_pdf

        with patch.dict("sys.modules", {"pdfplumber": mock_pdfplumber}):
            proc = PdfProcessor()
            chunks = proc._process_pdfplumber(f)
            assert len(chunks) == 1
            assert chunks[0].text == "Page 1 via pdfplumber"
            assert chunks[0].metadata["extraction_method"] == "pdfplumber"

    def test_raises_if_no_library(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_text("")
        proc = PdfProcessor()

        with patch.object(proc, "_process_pymupdf", side_effect=ImportError):
            with patch.object(proc, "_process_pdfplumber", side_effect=ImportError):
                with pytest.raises(ImportError, match="pymupdf or pdfplumber"):
                    proc.process(f)


# --- Ingest ---


class TestIngest:
    def test_ingest_file(self, tmp_path):
        md = tmp_path / "doc.md"
        md.write_text("# Title\nSome content here.")

        mock_kg = MagicMock()
        mock_kg.register_source = MagicMock()
        mock_kg.add_content = MagicMock()

        from video_processor.processors.ingest import ingest_file

        count = ingest_file(md, mock_kg)
        assert count == 1
        mock_kg.register_source.assert_called_once()
        source_arg = mock_kg.register_source.call_args[0][0]
        assert source_arg["source_type"] == "document"
        assert source_arg["title"] == "doc"
        mock_kg.add_content.assert_called_once()

    def test_ingest_file_unsupported(self, tmp_path):
        f = tmp_path / "data.xyz"
        f.write_text("stuff")
        mock_kg = MagicMock()

        from video_processor.processors.ingest import ingest_file

        with pytest.raises(ValueError, match="No processor"):
            ingest_file(f, mock_kg)

    def test_ingest_directory(self, tmp_path):
        (tmp_path / "a.md").write_text("# A\nContent A")
        (tmp_path / "b.txt").write_text("Content B")
        (tmp_path / "c.xyz").write_text("Ignored")

        mock_kg = MagicMock()

        from video_processor.processors.ingest import ingest_directory

        results = ingest_directory(tmp_path, mock_kg, recursive=False)
        # Should process a.md and b.txt but not c.xyz
        assert len(results) == 2
        processed_names = {Path(p).name for p in results}
        assert "a.md" in processed_names
        assert "b.txt" in processed_names

    def test_ingest_directory_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "top.md").write_text("# Top\nTop level")
        (sub / "nested.md").write_text("# Nested\nNested content")

        mock_kg = MagicMock()

        from video_processor.processors.ingest import ingest_directory

        results = ingest_directory(tmp_path, mock_kg, recursive=True)
        assert len(results) == 2
        processed_names = {Path(p).name for p in results}
        assert "top.md" in processed_names
        assert "nested.md" in processed_names

    def test_ingest_file_custom_source_id(self, tmp_path):
        md = tmp_path / "doc.md"
        md.write_text("# Title\nContent")

        mock_kg = MagicMock()

        from video_processor.processors.ingest import ingest_file

        ingest_file(md, mock_kg, source_id="custom-123")
        source_arg = mock_kg.register_source.call_args[0][0]
        assert source_arg["source_id"] == "custom-123"

    def test_ingest_content_source_format_with_section(self, tmp_path):
        md = tmp_path / "doc.md"
        md.write_text("# Introduction\nSome text\n\n## Details\nMore text")

        mock_kg = MagicMock()

        from video_processor.processors.ingest import ingest_file

        ingest_file(md, mock_kg)
        # Check content_source includes section info
        calls = mock_kg.add_content.call_args_list
        assert len(calls) == 2
        assert "document:doc.md:section:Introduction" in calls[0][0][1]
        assert "document:doc.md:section:Details" in calls[1][0][1]
