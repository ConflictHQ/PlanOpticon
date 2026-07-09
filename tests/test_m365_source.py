"""Tests for the Microsoft 365 (SharePoint/OneDrive) source connector.

These modules talk to Microsoft Graph through the `m365` CLI (cli-microsoft365)
via ``subprocess``, not the ``requests`` library. The real boundary is therefore
``_run_m365`` (and ``subprocess.run`` inside it) plus ``shutil.which`` for auth —
those are the only things mocked here. The filesystem is exercised for real via
``tmp_path`` and injected fake extraction libraries run the real mapping code.
"""

import json
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from video_processor.sources.base import SourceFile
from video_processor.sources.m365_source import (
    M365Source,
    _extract_text,
    _result_to_source_file,
    _run_m365,
)

M365 = "video_processor.sources.m365_source"


class TestRunM365:
    @patch(f"{M365}.subprocess.run")
    def test_returns_parsed_json(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"connectedAs": "user@contoso.com"}', stderr=""
        )
        result = _run_m365(["status"], timeout=42)
        assert result == {"connectedAs": "user@contoso.com"}
        # Command is built as: m365 <args> --output json
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "m365"
        assert cmd[1] == "status"
        assert cmd[-2:] == ["--output", "json"]
        # The timeout is forwarded to subprocess.run
        assert mock_run.call_args.kwargs["timeout"] == 42

    @patch(f"{M365}.subprocess.run")
    def test_returns_stripped_string_on_non_json(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="  not-json output  ", stderr="")
        result = _run_m365(["status"])
        assert result == "not-json output"

    @patch(f"{M365}.subprocess.run")
    def test_raises_runtimeerror_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="  login required  ")
        with pytest.raises(RuntimeError, match="login required"):
            _run_m365(["spo", "file", "list"])


class TestM365Constructor:
    def test_defaults(self):
        src = M365Source(web_url="https://contoso.sharepoint.com/sites/proj")
        assert src.web_url == "https://contoso.sharepoint.com/sites/proj"
        assert src.folder_url is None
        assert src.file_ids == []
        assert src.recursive is False

    def test_with_options(self):
        src = M365Source(
            web_url="https://contoso.sharepoint.com",
            folder_url="/sites/proj/docs",
            file_ids=["a", "b"],
            recursive=True,
        )
        assert src.folder_url == "/sites/proj/docs"
        assert src.file_ids == ["a", "b"]
        assert src.recursive is True


class TestM365Authenticate:
    @patch(f"{M365}.shutil.which", return_value=None)
    def test_cli_not_installed(self, _which):
        src = M365Source(web_url="https://contoso.sharepoint.com")
        assert src.authenticate() is False

    @patch(f"{M365}._run_m365")
    @patch(f"{M365}.shutil.which", return_value="/usr/local/bin/m365")
    def test_connected_dict(self, _which, mock_run):
        mock_run.return_value = {"connectedAs": "user@contoso.com"}
        assert M365Source(web_url="https://x.sharepoint.com").authenticate() is True

    @patch(f"{M365}._run_m365")
    @patch(f"{M365}.shutil.which", return_value="/usr/local/bin/m365")
    def test_logged_in_string(self, _which, mock_run):
        mock_run.return_value = "Logged in to contoso"
        assert M365Source(web_url="https://x.sharepoint.com").authenticate() is True

    @patch(f"{M365}._run_m365")
    @patch(f"{M365}.shutil.which", return_value="/usr/local/bin/m365")
    def test_not_logged_in(self, _which, mock_run):
        mock_run.return_value = {}
        assert M365Source(web_url="https://x.sharepoint.com").authenticate() is False

    @patch(f"{M365}._run_m365")
    @patch(f"{M365}.shutil.which", return_value="/usr/local/bin/m365")
    def test_runtime_error_returns_false(self, _which, mock_run):
        mock_run.side_effect = RuntimeError("status failed")
        assert M365Source(web_url="https://x.sharepoint.com").authenticate() is False

    @patch(f"{M365}._run_m365")
    @patch(f"{M365}.shutil.which", return_value="/usr/local/bin/m365")
    def test_timeout_returns_false(self, _which, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("m365", 10)
        assert M365Source(web_url="https://x.sharepoint.com").authenticate() is False


class TestM365ListVideos:
    @patch(f"{M365}._run_m365")
    def test_by_file_ids(self, mock_run):
        mock_run.return_value = {
            "Name": "report.pdf",
            "UniqueId": "uid-1",
            "Length": "50000",
            "ServerRelativeUrl": "/sites/proj/report.pdf",
        }
        src = M365Source(web_url="https://x.sharepoint.com", file_ids=["uid-1"])
        files = src.list_videos()
        assert len(files) == 1
        assert files[0].name == "report.pdf"
        assert files[0].id == "uid-1"
        assert files[0].path == "/sites/proj/report.pdf"
        args = mock_run.call_args[0][0]
        assert "spo" in args and "file" in args and "get" in args
        assert "--id" in args and "uid-1" in args

    @patch(f"{M365}._run_m365")
    def test_file_ids_error_is_skipped(self, mock_run):
        mock_run.side_effect = [
            RuntimeError("not found"),
            {"Name": "ok.docx", "UniqueId": "uid-2", "ServerRelativeUrl": "/f/ok.docx"},
        ]
        src = M365Source(web_url="https://x.sharepoint.com", file_ids=["bad", "uid-2"])
        files = src.list_videos()
        assert len(files) == 1
        assert files[0].name == "ok.docx"

    def test_no_folder_returns_empty(self):
        src = M365Source(web_url="https://x.sharepoint.com")
        assert src.list_videos() == []

    @patch(f"{M365}._run_m365")
    def test_folder_listing_filters_by_extension(self, mock_run):
        mock_run.return_value = [
            {"Name": "spec.docx", "UniqueId": "1", "ServerRelativeUrl": "/f/spec.docx"},
            {"Name": "photo.png", "UniqueId": "2", "ServerRelativeUrl": "/f/photo.png"},
            {"Name": "data.csv", "UniqueId": "3", "ServerRelativeUrl": "/f/data.csv"},
        ]
        src = M365Source(web_url="https://x.sharepoint.com", folder_url="/f")
        files = src.list_videos()
        # .png is not a document extension and is dropped.
        assert [f.name for f in files] == ["spec.docx", "data.csv"]

    @patch(f"{M365}._run_m365")
    def test_folder_path_argument_overrides_none(self, mock_run):
        mock_run.return_value = []
        src = M365Source(web_url="https://x.sharepoint.com")  # no folder_url
        src.list_videos(folder_path="/passed/folder")
        args = mock_run.call_args[0][0]
        assert "--folderUrl" in args
        assert "/passed/folder" in args

    @patch(f"{M365}._run_m365")
    def test_recursive_flag_added(self, mock_run):
        mock_run.return_value = []
        src = M365Source(web_url="https://x.sharepoint.com", folder_url="/f", recursive=True)
        src.list_videos()
        assert "--recursive" in mock_run.call_args[0][0]

    @patch(f"{M365}._run_m365")
    def test_non_list_result_yields_no_files(self, mock_run):
        mock_run.return_value = {"unexpected": "shape"}
        src = M365Source(web_url="https://x.sharepoint.com", folder_url="/f")
        assert src.list_videos() == []

    @patch(f"{M365}._run_m365")
    def test_listing_error_returns_empty(self, mock_run):
        mock_run.side_effect = RuntimeError("list boom")
        src = M365Source(web_url="https://x.sharepoint.com", folder_url="/f")
        assert src.list_videos() == []


class TestM365Download:
    @patch(f"{M365}._run_m365")
    def test_download_with_url(self, mock_run, tmp_path):
        src = M365Source(web_url="https://x.sharepoint.com")
        f = SourceFile(name="doc.docx", id="uid-1", path="/f/doc.docx")
        dest = tmp_path / "nested" / "doc.docx"
        result = src.download(f, dest)
        assert result == dest
        # download() really creates the parent directory (fs not mocked).
        assert dest.parent.is_dir()
        args = mock_run.call_args[0][0]
        assert "--url" in args and "/f/doc.docx" in args
        assert "--path" in args and str(dest) in args
        assert "--id" not in args

    @patch(f"{M365}._run_m365")
    def test_download_with_id(self, mock_run, tmp_path):
        src = M365Source(web_url="https://x.sharepoint.com")
        f = SourceFile(name="doc.docx", id="uid-9")  # no path field
        dest = tmp_path / "doc.docx"
        src.download(f, dest)
        args = mock_run.call_args[0][0]
        assert "--id" in args and "uid-9" in args
        assert "--url" not in args


class TestM365DownloadAsText:
    @patch(f"{M365}._run_m365")
    def test_text_ext_returns_string(self, mock_run):
        mock_run.return_value = "line one\nline two"
        src = M365Source(web_url="https://x.sharepoint.com")
        f = SourceFile(name="notes.txt", id="1", path="/f/notes.txt")
        assert src.download_as_text(f) == "line one\nline two"
        args = mock_run.call_args[0][0]
        assert "--asString" in args and "--url" in args

    @patch(f"{M365}._run_m365")
    def test_text_ext_dict_result_is_json_dumped(self, mock_run):
        mock_run.return_value = {"key": "value"}
        src = M365Source(web_url="https://x.sharepoint.com")
        f = SourceFile(name="data.csv", id="1")  # no path -> falls back to --id
        result = src.download_as_text(f)
        assert result == json.dumps({"key": "value"})
        assert "--id" in mock_run.call_args[0][0]

    @patch(f"{M365}._run_m365")
    def test_text_ext_error_falls_back_to_binary_download(self, mock_run):
        # First call (--asString) fails; the fallback download writes the file.
        def fake(args, timeout=30):
            if "--asString" in args:
                raise RuntimeError("asString unsupported")
            path = args[args.index("--path") + 1]
            Path(path).write_text("recovered body text")
            return None

        mock_run.side_effect = fake
        src = M365Source(web_url="https://x.sharepoint.com")
        f = SourceFile(name="notes.txt", id="1", path="/f/notes.txt")
        assert src.download_as_text(f) == "recovered body text"

    @patch(f"{M365}._run_m365")
    def test_binary_ext_uses_temp_and_extractor(self, mock_run):
        mock_run.return_value = None
        src = M365Source(web_url="https://x.sharepoint.com")
        # .pptx skips the text branch; _extract_text has no pptx handler.
        f = SourceFile(name="deck.pptx", id="1", path="/f/deck.pptx")
        result = src.download_as_text(f)
        assert "Unsupported format" in result


class TestM365FetchAllTextAndCollate:
    @patch(f"{M365}._run_m365")
    def test_fetch_all_text_happy(self, mock_run):
        mock_run.side_effect = [
            # list_videos folder listing
            [{"Name": "a.txt", "UniqueId": "1", "ServerRelativeUrl": "/f/a.txt"}],
            # download_as_text (--asString) for a.txt
            "content of A",
        ]
        src = M365Source(web_url="https://x.sharepoint.com", folder_url="/f")
        assert src.fetch_all_text() == {"a.txt": "content of A"}

    def test_fetch_all_text_captures_errors(self):
        src = M365Source(web_url="https://x.sharepoint.com", folder_url="/f")
        f = SourceFile(name="broken.txt", id="1")
        with (
            patch.object(src, "list_videos", return_value=[f]),
            patch.object(src, "download_as_text", side_effect=Exception("kaboom")),
        ):
            result = src.fetch_all_text()
        assert result == {"broken.txt": "[Error: kaboom]"}

    def test_collate_joins_documents(self):
        src = M365Source(web_url="https://x.sharepoint.com")
        with patch.object(src, "fetch_all_text", return_value={"a.txt": "AAA", "b.md": "BBB"}):
            result = src.collate(separator="\n===\n")
        assert "# a.txt\n\nAAA" in result
        assert "# b.md\n\nBBB" in result
        assert "\n===\n" in result


class TestResultToSourceFile:
    def test_sharepoint_pascalcase(self):
        sf = _result_to_source_file(
            {
                "Name": "spec.docx",
                "UniqueId": "uid-1",
                "Length": "2048",
                "ServerRelativeUrl": "/f/spec.docx",
                "TimeLastModified": "2026-01-01T00:00:00Z",
            }
        )
        assert sf.name == "spec.docx"
        assert sf.id == "uid-1"
        assert sf.size_bytes == 2048
        assert sf.path == "/f/spec.docx"
        assert sf.modified_at == "2026-01-01T00:00:00Z"
        assert sf.mime_type is None

    def test_graph_camelcase(self):
        sf = _result_to_source_file(
            {
                "name": "notes.md",
                "uniqueId": "gid-2",
                "length": "512",
                "serverRelativeUrl": "/f/notes.md",
                "lastModifiedDateTime": "2026-02-02",
            }
        )
        assert sf.name == "notes.md"
        assert sf.id == "gid-2"
        assert sf.size_bytes == 512
        assert sf.path == "/f/notes.md"
        assert sf.modified_at == "2026-02-02"

    def test_id_and_size_third_fallbacks(self):
        sf = _result_to_source_file({"id": "plain-id", "size": 100})
        assert sf.id == "plain-id"
        assert sf.size_bytes == 100

    def test_missing_fields_use_defaults(self):
        sf = _result_to_source_file({})
        assert sf.name == "Untitled"
        assert sf.id == ""
        assert sf.size_bytes is None
        assert sf.path is None


class TestExtractText:
    def test_txt(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("plain text body")
        assert _extract_text(f) == "plain text body"

    def test_md(self, tmp_path):
        f = tmp_path / "a.md"
        f.write_text("# Heading\n\nsome body")
        result = _extract_text(f)
        assert "# Heading" in result
        assert "some body" in result

    def test_csv(self, tmp_path):
        f = tmp_path / "a.csv"
        f.write_text("a,b,c\n1,2,3")
        assert "a,b,c" in _extract_text(f)

    def test_html_strips_tags(self, tmp_path):
        f = tmp_path / "a.html"
        f.write_text("<html><body><p>Hello <b>World</b></p></body></html>")
        result = _extract_text(f)
        assert "Hello" in result and "World" in result
        assert "<p>" not in result

    def test_pdf_missing_dependency(self, tmp_path):
        f = tmp_path / "a.pdf"
        f.write_bytes(b"%PDF-fake")
        # Force the ImportError branch even though pymupdf is installed.
        with patch.dict(sys.modules, {"fitz": None}):
            result = _extract_text(f)
        assert "install pymupdf" in result

    def test_pdf_extracts_with_fake_fitz(self, tmp_path):
        f = tmp_path / "a.pdf"
        f.write_bytes(b"%PDF-fake")
        page1 = MagicMock()
        page1.get_text.return_value = "Page one text"
        page2 = MagicMock()
        page2.get_text.return_value = "Page two text"
        fake_fitz = types.ModuleType("fitz")
        fake_fitz.open = MagicMock(return_value=[page1, page2])
        with patch.dict(sys.modules, {"fitz": fake_fitz}):
            result = _extract_text(f)
        assert "Page one text" in result
        assert "Page two text" in result
        fake_fitz.open.assert_called_once_with(str(f))

    def test_docx_missing_dependency(self, tmp_path):
        f = tmp_path / "a.docx"
        f.write_bytes(b"PK\x03\x04")
        result = _extract_text(f)  # python-docx is not installed
        assert "install python-docx" in result

    def test_docx_extracts_with_fake_lib(self, tmp_path):
        f = tmp_path / "a.docx"
        f.write_bytes(b"PK\x03\x04")
        para1 = MagicMock(text="First para")
        para_blank = MagicMock(text="   ")
        para2 = MagicMock(text="Second para")
        fake_doc = MagicMock(paragraphs=[para1, para_blank, para2])
        fake_docx = types.ModuleType("docx")
        fake_docx.Document = MagicMock(return_value=fake_doc)
        with patch.dict(sys.modules, {"docx": fake_docx}):
            result = _extract_text(f)
        # Whitespace-only paragraph is filtered out.
        assert result == "First para\n\nSecond para"

    def test_xlsx_missing_dependency(self, tmp_path):
        f = tmp_path / "a.xlsx"
        f.write_bytes(b"PK\x03\x04")
        result = _extract_text(f)  # openpyxl is not installed
        assert "install python-docx/openpyxl" in result

    def test_xlsx_extracts_with_fake_lib(self, tmp_path):
        f = tmp_path / "a.xlsx"
        f.write_bytes(b"PK\x03\x04")
        ws = MagicMock()
        ws.iter_rows.return_value = [("Name", "Score"), ("Alice", 10), (None, None)]
        fake_wb = MagicMock()
        fake_wb.sheetnames = ["Sheet1"]
        fake_wb.__getitem__.return_value = ws
        fake_openpyxl = types.ModuleType("openpyxl")
        fake_openpyxl.load_workbook = MagicMock(return_value=fake_wb)
        with patch.dict(sys.modules, {"openpyxl": fake_openpyxl}):
            result = _extract_text(f)
        assert "Name\tScore" in result
        assert "Alice\t10" in result
        # The all-empty row is skipped entirely.
        assert result == "Name\tScore\nAlice\t10"

    def test_pptx_is_unsupported(self, tmp_path):
        f = tmp_path / "a.pptx"
        f.write_bytes(b"PK\x03\x04")
        assert "Unsupported format" in _extract_text(f)

    def test_unknown_extension_is_unsupported(self, tmp_path):
        f = tmp_path / "a.xyz"
        f.write_bytes(b"stuff")
        assert "Unsupported format" in _extract_text(f)
