"""Tests for the OneNote source.

NOTE: despite the connector's module docstring, this source does NOT use the
Microsoft Graph ``requests`` API. It shells out to the ``m365`` CLI
(cli-microsoft365) via ``subprocess`` and parses its JSON output. These tests
therefore patch ``subprocess.run`` (for the ``_run_m365`` helper) and the
``_run_m365`` / ``shutil.which`` module attributes (for higher-level methods);
the real CLI and network are never touched. Page downloads are written to real
``tmp_path`` files and asserted against their parsed text content.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from video_processor.sources.base import SourceFile
from video_processor.sources.onenote_source import OneNoteSource, _html_to_text, _run_m365

MODULE = "video_processor.sources.onenote_source"


class TestRunM365:
    def test_success_parses_json(self):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = '{"connectedAs": "user@example.com"}'
        proc.stderr = ""
        with patch(f"{MODULE}.subprocess.run", return_value=proc) as run:
            result = _run_m365(["status"], timeout=10)
        assert result == {"connectedAs": "user@example.com"}
        cmd = run.call_args.args[0]
        assert cmd == ["m365", "status", "--output", "json"]
        assert run.call_args.kwargs["timeout"] == 10

    def test_non_json_output_returned_as_stripped_text(self):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "Logged in as user@example.com\n"
        proc.stderr = ""
        with patch(f"{MODULE}.subprocess.run", return_value=proc):
            result = _run_m365(["status"])
        assert result == "Logged in as user@example.com"

    def test_nonzero_exit_raises_runtime_error(self):
        proc = MagicMock()
        proc.returncode = 1
        proc.stdout = ""
        proc.stderr = "  authentication required  "
        with patch(f"{MODULE}.subprocess.run", return_value=proc):
            with pytest.raises(RuntimeError, match="authentication required"):
                _run_m365(["onenote", "notebook", "list"])


class TestHtmlToText:
    def test_strips_script_and_style_blocks(self):
        html = "<style>p{color:red}</style><script>alert(1)</script>Visible"
        assert _html_to_text(html) == "Visible"

    def test_block_close_tags_become_newlines(self):
        assert _html_to_text("<p>alpha</p><p>beta</p>") == "alpha\nbeta"

    def test_br_becomes_newline(self):
        assert _html_to_text("line1<br>line2<br/>line3") == "line1\nline2\nline3"

    def test_named_entities_decoded(self):
        assert _html_to_text("Tom &amp; Jerry &lt;3 &quot;x&quot;") == 'Tom & Jerry <3 "x"'

    def test_nbsp_and_apostrophe_entities(self):
        assert _html_to_text("a&nbsp;b&#39;c&apos;d") == "a b'c'd"

    def test_numeric_entities_decimal_and_hex(self):
        assert _html_to_text("&#65;&#x42;&#67;") == "ABC"

    def test_inline_tags_stripped(self):
        assert _html_to_text("<b>bold</b> and <i>italic</i>") == "bold and italic"

    def test_collapses_excess_blank_lines(self):
        assert _html_to_text("a<br><br><br><br>b") == "a\n\nb"

    def test_realistic_page(self):
        html = (
            "<html><head><style>x{}</style></head><body>"
            "<h1>Meeting Notes</h1>"
            "<p>Discussed &amp; agreed on the <b>roadmap</b>.</p>"
            "<div>Action: ship v1</div>"
            "</body></html>"
        )
        text = _html_to_text(html)
        assert "<" not in text
        assert ">" not in text
        assert "Meeting Notes" in text
        assert "Discussed & agreed on the roadmap." in text
        assert "Action: ship v1" in text


class TestOneNoteInit:
    def test_defaults(self):
        source = OneNoteSource()
        assert source.notebook_name is None
        assert source.section_name is None

    def test_with_names(self):
        source = OneNoteSource(notebook_name="Work", section_name="Meetings")
        assert source.notebook_name == "Work"
        assert source.section_name == "Meetings"


class TestOneNoteAuthenticate:
    def test_cli_not_installed_returns_false(self):
        source = OneNoteSource()
        with patch(f"{MODULE}.shutil.which", return_value=None):
            assert source.authenticate() is False

    def test_connected_via_dict_status(self):
        source = OneNoteSource()
        with patch(f"{MODULE}.shutil.which", return_value="/usr/bin/m365"):
            with patch(f"{MODULE}._run_m365", return_value={"connectedAs": "user@x.com"}):
                assert source.authenticate() is True

    def test_connected_via_text_status(self):
        source = OneNoteSource()
        with patch(f"{MODULE}.shutil.which", return_value="/usr/bin/m365"):
            with patch(f"{MODULE}._run_m365", return_value="Logged in as user@x.com"):
                assert source.authenticate() is True

    def test_not_logged_in_dict_returns_false(self):
        source = OneNoteSource()
        with patch(f"{MODULE}.shutil.which", return_value="/usr/bin/m365"):
            with patch(f"{MODULE}._run_m365", return_value={"foo": "bar"}):
                assert source.authenticate() is False

    def test_runtime_error_treated_as_not_logged_in(self):
        source = OneNoteSource()
        with patch(f"{MODULE}.shutil.which", return_value="/usr/bin/m365"):
            with patch(f"{MODULE}._run_m365", side_effect=RuntimeError("boom")):
                assert source.authenticate() is False

    def test_timeout_treated_as_not_logged_in(self):
        source = OneNoteSource()
        with patch(f"{MODULE}.shutil.which", return_value="/usr/bin/m365"):
            with patch(
                f"{MODULE}._run_m365",
                side_effect=subprocess.TimeoutExpired(cmd="m365", timeout=10),
            ):
                assert source.authenticate() is False


class TestOneNoteListVideos:
    def test_notebook_listing_failure_returns_empty(self):
        source = OneNoteSource()
        with patch(f"{MODULE}._run_m365", side_effect=RuntimeError("graph unreachable")):
            assert source.list_videos() == []

    def test_full_traversal_builds_sourcefiles(self):
        source = OneNoteSource()
        responses = [
            [{"id": "nb1", "displayName": "Work"}],  # notebook list
            [{"id": "sec1", "displayName": "Meetings"}],  # section list
            [
                {
                    "id": "pg1",
                    "title": "Standup",
                    "lastModifiedDateTime": "2025-03-01T09:00:00Z",
                }
            ],  # page list
        ]
        with patch(f"{MODULE}._run_m365", side_effect=responses):
            files = source.list_videos()
        assert len(files) == 1
        page = files[0]
        assert page.name == "Standup"
        assert page.id == "pg1"
        assert page.mime_type == "text/html"
        assert page.modified_at == "2025-03-01T09:00:00Z"
        assert page.size_bytes is None
        assert page.path == "Work/Meetings/Standup"

    def test_notebook_name_filter(self):
        source = OneNoteSource(notebook_name="work")
        responses = [
            [
                {"id": "nb1", "displayName": "Work Notes"},
                {"id": "nb2", "displayName": "Personal"},
            ],
            [{"id": "sec1", "displayName": "General"}],  # sections for Work Notes only
            [{"id": "pg1", "title": "Note A"}],  # pages for that section
        ]
        with patch(f"{MODULE}._run_m365", side_effect=responses) as run:
            files = source.list_videos()
        assert [f.path for f in files] == ["Work Notes/General/Note A"]
        # Only the matching notebook is traversed: notebook + section + page = 3 calls.
        assert run.call_count == 3

    def test_section_name_filter(self):
        source = OneNoteSource(section_name="meet")
        responses = [
            [{"id": "nb1", "displayName": "Work"}],
            [
                {"id": "sec1", "displayName": "Meetings"},
                {"id": "sec2", "displayName": "Scratch"},
            ],
            [{"id": "pg1", "title": "Kickoff"}],  # pages for Meetings only
        ]
        with patch(f"{MODULE}._run_m365", side_effect=responses) as run:
            files = source.list_videos()
        assert [f.path for f in files] == ["Work/Meetings/Kickoff"]
        assert run.call_count == 3

    def test_notebooks_not_a_list_returns_empty(self):
        source = OneNoteSource()
        with patch(f"{MODULE}._run_m365", return_value="unexpected string"):
            assert source.list_videos() == []

    def test_section_listing_failure_skips_notebook(self):
        source = OneNoteSource()
        responses = [
            [{"id": "nb1", "displayName": "Work"}],
            RuntimeError("section list failed"),
        ]
        with patch(f"{MODULE}._run_m365", side_effect=responses):
            assert source.list_videos() == []

    def test_sections_not_a_list_skips(self):
        source = OneNoteSource()
        responses = [
            [{"id": "nb1", "displayName": "Work"}],
            {"unexpected": "dict"},
        ]
        with patch(f"{MODULE}._run_m365", side_effect=responses):
            assert source.list_videos() == []

    def test_page_listing_failure_skips_section(self):
        source = OneNoteSource()
        responses = [
            [{"id": "nb1", "displayName": "Work"}],
            [{"id": "sec1", "displayName": "Meetings"}],
            RuntimeError("page list failed"),
        ]
        with patch(f"{MODULE}._run_m365", side_effect=responses):
            assert source.list_videos() == []

    def test_pages_not_a_list_skips(self):
        source = OneNoteSource()
        responses = [
            [{"id": "nb1", "displayName": "Work"}],
            [{"id": "sec1", "displayName": "Meetings"}],
            "not a list",
        ]
        with patch(f"{MODULE}._run_m365", side_effect=responses):
            assert source.list_videos() == []

    def test_untitled_page_fallback(self):
        source = OneNoteSource()
        responses = [
            [{"id": "nb1", "displayName": "Work"}],
            [{"id": "sec1", "displayName": "Meetings"}],
            [
                {"id": "pg1", "title": "   "},  # whitespace-only title
                {"id": "pg2"},  # missing title entirely
            ],
        ]
        with patch(f"{MODULE}._run_m365", side_effect=responses):
            files = source.list_videos()
        assert [f.name for f in files] == ["Untitled Page", "Untitled Page"]


class TestOneNoteDownload:
    def test_dict_content_written_as_text(self, tmp_path):
        source = OneNoteSource()
        dest = tmp_path / "notes" / "page.txt"
        with patch(f"{MODULE}._run_m365", return_value={"content": "<p>Hello &amp; welcome</p>"}):
            result = source.download(SourceFile(name="Page", id="pg1"), dest)
        assert result == dest
        assert dest.read_text(encoding="utf-8") == "Hello & welcome"

    def test_body_content_fallback(self, tmp_path):
        source = OneNoteSource()
        dest = tmp_path / "page.txt"
        with patch(f"{MODULE}._run_m365", return_value={"body": {"content": "<b>Body text</b>"}}):
            result = source.download(SourceFile(name="P", id="pg1"), dest)
        assert result.read_text(encoding="utf-8") == "Body text"

    def test_empty_dict_serialized_as_json(self, tmp_path):
        source = OneNoteSource()
        dest = tmp_path / "page.txt"
        with patch(f"{MODULE}._run_m365", return_value={"id": "pg1", "misc": 5}):
            source.download(SourceFile(name="P", id="pg1"), dest)
        text = dest.read_text(encoding="utf-8")
        assert '"id": "pg1"' in text
        assert '"misc": 5' in text

    def test_string_result_written(self, tmp_path):
        source = OneNoteSource()
        dest = tmp_path / "page.txt"
        with patch(f"{MODULE}._run_m365", return_value="raw <i>text</i> here"):
            source.download(SourceFile(name="P", id="pg1"), dest)
        assert dest.read_text(encoding="utf-8") == "raw text here"

    def test_other_type_result_stringified(self, tmp_path):
        source = OneNoteSource()
        dest = tmp_path / "page.txt"
        with patch(f"{MODULE}._run_m365", return_value=[1, 2, 3]):
            source.download(SourceFile(name="P", id="pg1"), dest)
        assert dest.read_text(encoding="utf-8") == "[1, 2, 3]"

    def test_fetch_failure_raises_runtime_error(self, tmp_path):
        source = OneNoteSource()
        dest = tmp_path / "page.txt"
        with patch(f"{MODULE}._run_m365", side_effect=RuntimeError("network down")):
            with pytest.raises(RuntimeError, match="Failed to fetch OneNote page pg1"):
                source.download(SourceFile(name="P", id="pg1"), dest)
