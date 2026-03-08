"""Tests for PDF and PPTX exporters."""

import pytest

from video_processor.exporters.pdf_export import generate_pdf
from video_processor.exporters.pptx_export import generate_pptx


def _sample_kg():
    """Return a sample knowledge graph dict for testing."""
    return {
        "nodes": [
            {"name": "Python", "type": "technology", "descriptions": ["A programming language"]},
            {"name": "Django", "type": "technology", "descriptions": ["A web framework"]},
            {"name": "Alice", "type": "person", "descriptions": ["Software engineer"]},
            {"name": "Bob", "type": "person", "descriptions": ["Product manager"]},
            {"name": "Acme Corp", "type": "organization", "descriptions": ["A tech company"]},
        ],
        "relationships": [
            {"source": "Alice", "target": "Python", "type": "uses"},
            {"source": "Alice", "target": "Bob", "type": "works_with"},
            {"source": "Django", "target": "Python", "type": "built_on"},
            {"source": "Alice", "target": "Acme Corp", "type": "employed_by"},
        ],
    }


def _empty_kg():
    return {"nodes": [], "relationships": []}


class TestPDFExport:
    @pytest.fixture(autouse=True)
    def _check_reportlab(self):
        pytest.importorskip("reportlab")

    def test_generate_pdf(self, tmp_path):
        out = tmp_path / "report.pdf"
        result = generate_pdf(_sample_kg(), out, title="Test Report")
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 0

    def test_generate_pdf_empty_kg(self, tmp_path):
        out = tmp_path / "empty.pdf"
        result = generate_pdf(_empty_kg(), out)
        assert result == out
        assert out.exists()

    def test_generate_pdf_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "sub" / "dir" / "report.pdf"
        result = generate_pdf(_sample_kg(), out)
        assert result == out
        assert out.exists()

    def test_generate_pdf_default_title(self, tmp_path):
        out = tmp_path / "default.pdf"
        generate_pdf(_sample_kg(), out)
        assert out.exists()

    def test_generate_pdf_with_diagrams_dir(self, tmp_path):
        diag_dir = tmp_path / "diagrams"
        diag_dir.mkdir()
        out = tmp_path / "report.pdf"
        # No PNGs in dir — should still work
        result = generate_pdf(_sample_kg(), out, diagrams_dir=diag_dir)
        assert result == out

    def test_generate_pdf_no_reportlab(self, tmp_path, monkeypatch):
        """Verify ImportError propagates when reportlab is missing."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name.startswith("reportlab"):
                raise ImportError("No module named 'reportlab'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        with pytest.raises(ImportError):
            generate_pdf(_sample_kg(), tmp_path / "fail.pdf")


class TestPPTXExport:
    @pytest.fixture(autouse=True)
    def _check_pptx(self):
        pytest.importorskip("pptx")

    def test_generate_pptx(self, tmp_path):
        out = tmp_path / "slides.pptx"
        result = generate_pptx(_sample_kg(), out, title="Test Deck")
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 0

    def test_generate_pptx_empty_kg(self, tmp_path):
        out = tmp_path / "empty.pptx"
        result = generate_pptx(_empty_kg(), out)
        assert result == out
        assert out.exists()

    def test_generate_pptx_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "sub" / "dir" / "slides.pptx"
        result = generate_pptx(_sample_kg(), out)
        assert result == out
        assert out.exists()

    def test_generate_pptx_with_diagrams_dir(self, tmp_path):
        diag_dir = tmp_path / "diagrams"
        diag_dir.mkdir()
        out = tmp_path / "slides.pptx"
        result = generate_pptx(_sample_kg(), out, diagrams_dir=diag_dir)
        assert result == out

    def test_pptx_slide_count(self, tmp_path):
        """Verify expected number of slides are created."""
        from pptx import Presentation

        out = tmp_path / "count.pptx"
        generate_pptx(_sample_kg(), out)
        prs = Presentation(str(out))
        # Title + Overview + Key Entities + Rel Types + 1 entity batch = 5
        assert len(prs.slides) == 5

    def test_pptx_many_entities_batched(self, tmp_path):
        """Entities are batched into multiple slides when >12."""
        from pptx import Presentation

        kg = {
            "nodes": [
                {"name": f"Entity{i}", "type": "concept", "descriptions": [f"desc {i}"]}
                for i in range(25)
            ],
            "relationships": [],
        }
        out = tmp_path / "many.pptx"
        generate_pptx(kg, out)
        prs = Presentation(str(out))
        # Title + Overview + 3 entity batches (12 + 12 + 1) = 5
        # No Key Entities or Rel Types slides (no relationships)
        assert len(prs.slides) == 5

    def test_generate_pptx_no_pptx(self, tmp_path, monkeypatch):
        """Verify ImportError propagates when python-pptx is missing."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name.startswith("pptx"):
                raise ImportError("No module named 'pptx'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        with pytest.raises(ImportError):
            generate_pptx(_sample_kg(), tmp_path / "fail.pptx")
