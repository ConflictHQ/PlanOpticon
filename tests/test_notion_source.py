"""Tests for the Notion API source connector.

Covers the pure markdown/property helpers plus the HTTP-backed methods.
The real ``requests`` module (and its exception classes) is left intact so
that ``except requests.RequestException`` still catches; only the ``get`` /
``post`` attributes on the module are patched.
"""

import logging
import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from video_processor.sources.base import SourceFile
from video_processor.sources.notion_source import (
    NOTION_VERSION,
    NotionSource,
    _extract_page_title,
    _extract_property_value,
    _rich_text_to_str,
)

# ---------------------------------------------------------------------------
# _rich_text_to_str
# ---------------------------------------------------------------------------


class TestRichTextToStr:
    def test_joins_plain_text(self):
        rich = [{"plain_text": "Hello "}, {"plain_text": "World"}]
        assert _rich_text_to_str(rich) == "Hello World"

    def test_empty_list(self):
        assert _rich_text_to_str([]) == ""

    def test_missing_plain_text_key(self):
        rich = [{"annotations": {}}, {"plain_text": "kept"}]
        assert _rich_text_to_str(rich) == "kept"


# ---------------------------------------------------------------------------
# _extract_page_title
# ---------------------------------------------------------------------------


class TestExtractPageTitle:
    def test_title_present(self):
        page = {"properties": {"Name": {"type": "title", "title": [{"plain_text": "My Page"}]}}}
        assert _extract_page_title(page) == "My Page"

    def test_untitled_fallback_when_no_title_prop(self):
        page = {
            "properties": {
                "Tags": {"type": "multi_select", "multi_select": []},
            }
        }
        assert _extract_page_title(page) == "Untitled"

    def test_untitled_fallback_when_no_properties(self):
        assert _extract_page_title({}) == "Untitled"


# ---------------------------------------------------------------------------
# _extract_property_value — one assertion per property type branch
# ---------------------------------------------------------------------------


class TestExtractPropertyValue:
    def test_title(self):
        prop = {"type": "title", "title": [{"plain_text": "The Title"}]}
        assert _extract_property_value(prop) == "The Title"

    def test_rich_text(self):
        prop = {"type": "rich_text", "rich_text": [{"plain_text": "some text"}]}
        assert _extract_property_value(prop) == "some text"

    def test_number(self):
        assert _extract_property_value({"type": "number", "number": 42}) == "42"

    def test_number_none(self):
        assert _extract_property_value({"type": "number", "number": None}) == ""

    def test_select(self):
        prop = {"type": "select", "select": {"name": "Done"}}
        assert _extract_property_value(prop) == "Done"

    def test_select_none(self):
        assert _extract_property_value({"type": "select", "select": None}) == ""

    def test_multi_select(self):
        prop = {
            "type": "multi_select",
            "multi_select": [{"name": "alpha"}, {"name": "beta"}],
        }
        assert _extract_property_value(prop) == "alpha; beta"

    def test_date_start_only(self):
        prop = {"type": "date", "date": {"start": "2025-01-01"}}
        assert _extract_property_value(prop) == "2025-01-01"

    def test_date_with_end(self):
        prop = {
            "type": "date",
            "date": {"start": "2025-01-01", "end": "2025-01-31"},
        }
        assert _extract_property_value(prop) == "2025-01-01 - 2025-01-31"

    def test_date_none(self):
        assert _extract_property_value({"type": "date", "date": None}) == ""

    def test_checkbox_true(self):
        assert _extract_property_value({"type": "checkbox", "checkbox": True}) == "True"

    def test_checkbox_false(self):
        prop = {"type": "checkbox", "checkbox": False}
        assert _extract_property_value(prop) == "False"

    def test_url(self):
        prop = {"type": "url", "url": "https://example.com"}
        assert _extract_property_value(prop) == "https://example.com"

    def test_url_none(self):
        assert _extract_property_value({"type": "url", "url": None}) == ""

    def test_email(self):
        prop = {"type": "email", "email": "person@example.com"}
        assert _extract_property_value(prop) == "person@example.com"

    def test_phone_number(self):
        prop = {"type": "phone_number", "phone_number": "555-1234"}
        assert _extract_property_value(prop) == "555-1234"

    def test_status(self):
        prop = {"type": "status", "status": {"name": "In Progress"}}
        assert _extract_property_value(prop) == "In Progress"

    def test_status_none(self):
        assert _extract_property_value({"type": "status", "status": None}) == ""

    def test_people(self):
        prop = {"type": "people", "people": [{"name": "Bob"}, {"name": "Carol"}]}
        assert _extract_property_value(prop) == "Bob; Carol"

    def test_relation(self):
        prop = {"type": "relation", "relation": [{"id": "rel-1"}, {"id": "rel-2"}]}
        assert _extract_property_value(prop) == "rel-1; rel-2"

    def test_formula_string(self):
        prop = {"type": "formula", "formula": {"type": "string", "string": "computed"}}
        assert _extract_property_value(prop) == "computed"

    def test_formula_number(self):
        prop = {"type": "formula", "formula": {"type": "number", "number": 7}}
        assert _extract_property_value(prop) == "7"

    def test_unknown_type(self):
        assert _extract_property_value({"type": "button"}) == ""

    def test_empty_prop(self):
        assert _extract_property_value({}) == ""


# ---------------------------------------------------------------------------
# NotionSource._blocks_to_text
# ---------------------------------------------------------------------------


class TestBlocksToText:
    def test_common_block_types(self):
        src = NotionSource(token="tok")
        blocks = [
            {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Para"}]}},
            {"type": "heading_1", "heading_1": {"rich_text": [{"plain_text": "H1"}]}},
            {"type": "heading_2", "heading_2": {"rich_text": [{"plain_text": "H2"}]}},
            {"type": "heading_3", "heading_3": {"rich_text": [{"plain_text": "H3"}]}},
            {
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"plain_text": "Bullet"}]},
            },
            {"type": "quote", "quote": {"rich_text": [{"plain_text": "Quoted"}]}},
            {"type": "toggle", "toggle": {"rich_text": [{"plain_text": "Toggle"}]}},
            {"type": "divider", "divider": {}},
        ]
        result = src._blocks_to_text(blocks)
        assert "Para" in result
        assert "# H1" in result
        assert "## H2" in result
        assert "### H3" in result
        assert "- Bullet" in result
        assert "> Quoted" in result
        assert "<details><summary>Toggle</summary></details>" in result
        assert "---" in result

    def test_numbered_list_increments_and_resets(self):
        src = NotionSource(token="tok")
        blocks = [
            {
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": [{"plain_text": "First"}]},
            },
            {
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": [{"plain_text": "Second"}]},
            },
            {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Break"}]}},
            {
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": [{"plain_text": "Reset"}]},
            },
        ]
        lines = src._blocks_to_text(blocks).split("\n\n")
        assert lines == ["1. First", "2. Second", "Break", "1. Reset"]

    def test_to_do_checked_and_unchecked(self):
        src = NotionSource(token="tok")
        blocks = [
            {
                "type": "to_do",
                "to_do": {"rich_text": [{"plain_text": "Done task"}], "checked": True},
            },
            {
                "type": "to_do",
                "to_do": {"rich_text": [{"plain_text": "Pending task"}]},
            },
        ]
        result = src._blocks_to_text(blocks)
        assert "- [x] Done task" in result
        assert "- [ ] Pending task" in result

    def test_code_block_with_language(self):
        src = NotionSource(token="tok")
        blocks = [
            {
                "type": "code",
                "code": {
                    "rich_text": [{"plain_text": "print('hi')"}],
                    "language": "python",
                },
            }
        ]
        result = src._blocks_to_text(blocks)
        assert "```python" in result
        assert "print('hi')" in result
        # opening fence + closing fence
        assert result.count("```") == 2

    def test_callout_with_emoji(self):
        src = NotionSource(token="tok")
        blocks = [
            {
                "type": "callout",
                "callout": {
                    "rich_text": [{"plain_text": "Heads up"}],
                    "icon": {"emoji": "\N{ELECTRIC LIGHT BULB}"},
                },
            }
        ]
        result = src._blocks_to_text(blocks)
        assert result == "> \N{ELECTRIC LIGHT BULB} Heads up"

    def test_callout_without_emoji(self):
        src = NotionSource(token="tok")
        blocks = [
            {
                "type": "callout",
                "callout": {"rich_text": [{"plain_text": "Plain callout"}]},
            }
        ]
        result = src._blocks_to_text(blocks)
        assert result == "> Plain callout"

    def test_unknown_block_with_rich_text(self):
        src = NotionSource(token="tok")
        blocks = [{"type": "image", "image": {"rich_text": [{"plain_text": "caption text"}]}}]
        assert src._blocks_to_text(blocks) == "caption text"

    def test_unknown_block_without_text_is_dropped(self):
        src = NotionSource(token="tok")
        blocks = [{"type": "image", "image": {}}]
        assert src._blocks_to_text(blocks) == ""

    def test_empty_block_list(self):
        src = NotionSource(token="tok")
        assert src._blocks_to_text([]) == ""


# ---------------------------------------------------------------------------
# NotionSource construction + headers
# ---------------------------------------------------------------------------


class TestNotionSourceInit:
    def test_explicit_arguments(self):
        src = NotionSource(token="tok", database_id="db-1", page_ids=["p1", "p2"])
        assert src.token == "tok"
        assert src.database_id == "db-1"
        assert src.page_ids == ["p1", "p2"]

    @patch.dict(os.environ, {}, clear=True)
    def test_defaults_without_env(self):
        src = NotionSource()
        assert src.token == ""
        assert src.database_id is None
        assert src.page_ids == []

    @patch.dict(os.environ, {"NOTION_API_KEY": "env-token"}, clear=True)
    def test_token_from_env(self):
        src = NotionSource()
        assert src.token == "env-token"

    def test_headers(self):
        src = NotionSource(token="tok123")
        headers = src._headers()
        assert headers["Authorization"] == "Bearer tok123"
        assert headers["Notion-Version"] == NOTION_VERSION
        assert headers["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# NotionSource.authenticate
# ---------------------------------------------------------------------------


class TestNotionSourceAuthenticate:
    @patch("video_processor.sources.notion_source.requests.get")
    @patch.dict(os.environ, {}, clear=True)
    def test_no_token_returns_false_without_http(self, mock_get):
        src = NotionSource(token="")
        assert src.authenticate() is False
        assert mock_get.call_count == 0

    @patch("video_processor.sources.notion_source.requests.get")
    def test_success(self, mock_get):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"name": "Test Bot"}
        mock_get.return_value = resp

        src = NotionSource(token="tok")
        assert src.authenticate() is True
        mock_get.assert_called_once()

    @patch("video_processor.sources.notion_source.requests.get")
    def test_http_error_returns_false(self, mock_get):
        resp = MagicMock()
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")
        mock_get.return_value = resp

        src = NotionSource(token="tok")
        assert src.authenticate() is False


# ---------------------------------------------------------------------------
# NotionSource.list_videos
# ---------------------------------------------------------------------------


class TestNotionSourceListVideos:
    @patch("video_processor.sources.notion_source.requests.post")
    def test_database_paginates(self, mock_post):
        page1 = MagicMock()
        page1.raise_for_status.return_value = None
        page1.json.return_value = {
            "results": [
                {
                    "id": "p1",
                    "last_edited_time": "t1",
                    "properties": {"Name": {"type": "title", "title": [{"plain_text": "First"}]}},
                }
            ],
            "has_more": True,
            "next_cursor": "cursor-2",
        }
        page2 = MagicMock()
        page2.raise_for_status.return_value = None
        page2.json.return_value = {
            "results": [
                {
                    "id": "p2",
                    "last_edited_time": "t2",
                    "properties": {"Name": {"type": "title", "title": [{"plain_text": "Second"}]}},
                }
            ],
            "has_more": False,
            "next_cursor": None,
        }
        mock_post.side_effect = [page1, page2]

        src = NotionSource(token="tok", database_id="db-1")
        files = src.list_videos()

        assert len(files) == 2
        assert files[0].name == "First"
        assert files[0].id == "p1"
        assert files[0].mime_type == "text/markdown"
        assert files[0].modified_at == "t1"
        assert files[1].name == "Second"
        assert files[1].id == "p2"
        assert mock_post.call_count == 2
        # second page must carry the cursor returned by the first page
        assert mock_post.call_args_list[1].kwargs["json"] == {"start_cursor": "cursor-2"}

    @patch("video_processor.sources.notion_source.requests.get")
    def test_from_page_ids(self, mock_get):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "id": "page-9",
            "last_edited_time": "t9",
            "properties": {"Title": {"type": "title", "title": [{"plain_text": "Page Nine"}]}},
        }
        mock_get.return_value = resp

        src = NotionSource(token="tok", page_ids=["page-9"])
        files = src.list_videos()

        assert len(files) == 1
        assert files[0].name == "Page Nine"
        assert files[0].id == "page-9"
        assert files[0].mime_type == "text/markdown"

    def test_no_source_returns_empty_and_warns(self, caplog):
        src = NotionSource(token="tok")
        with caplog.at_level(logging.WARNING):
            files = src.list_videos()
        assert files == []
        assert any("No pages found" in r.getMessage() for r in caplog.records)

    @patch("video_processor.sources.notion_source.requests.get")
    def test_page_ids_partial_failure(self, mock_get):
        good = MagicMock()
        good.raise_for_status.return_value = None
        good.json.return_value = {
            "id": "good-1",
            "last_edited_time": "t",
            "properties": {"Title": {"type": "title", "title": [{"plain_text": "Good Page"}]}},
        }

        def side_effect(url, **kwargs):
            if "bad-1" in url:
                raise requests.exceptions.ConnectionError("network down")
            return good

        mock_get.side_effect = side_effect

        src = NotionSource(token="tok", page_ids=["bad-1", "good-1"])
        files = src.list_videos()

        assert len(files) == 1
        assert files[0].name == "Good Page"
        assert files[0].id == "good-1"

    @patch("video_processor.sources.notion_source.requests.post")
    def test_database_error_propagates(self, mock_post):
        mock_post.side_effect = requests.exceptions.HTTPError("500")
        src = NotionSource(token="tok", database_id="db-1")
        with pytest.raises(requests.exceptions.HTTPError):
            src.list_videos()


# ---------------------------------------------------------------------------
# NotionSource.download / _fetch_all_blocks
# ---------------------------------------------------------------------------


class TestNotionSourceDownload:
    def test_download_writes_markdown_file(self, tmp_path):
        src = NotionSource(token="tok")
        blocks = [
            {"type": "heading_1", "heading_1": {"rich_text": [{"plain_text": "Section"}]}},
            {
                "type": "paragraph",
                "paragraph": {"rich_text": [{"plain_text": "Body text."}]},
            },
        ]
        f = SourceFile(name="My Page", id="pg-1", mime_type="text/markdown")
        # destination parent does not exist yet — download must create it
        dest = tmp_path / "out" / "page.md"

        with patch.object(src, "_fetch_all_blocks", return_value=blocks) as mock_fetch:
            result = src.download(f, dest)

        assert result == dest
        assert dest.exists()
        content = dest.read_text(encoding="utf-8")
        assert content.startswith("# My Page")
        assert "# Section" in content
        assert "Body text." in content
        mock_fetch.assert_called_once_with("pg-1")

    @patch("video_processor.sources.notion_source.requests.get")
    def test_fetch_all_blocks_paginates(self, mock_get):
        page1 = MagicMock()
        page1.raise_for_status.return_value = None
        page1.json.return_value = {
            "results": [{"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "A"}]}}],
            "has_more": True,
            "next_cursor": "cur-2",
        }
        page2 = MagicMock()
        page2.raise_for_status.return_value = None
        page2.json.return_value = {
            "results": [{"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "B"}]}}],
            "has_more": False,
            "next_cursor": None,
        }
        mock_get.side_effect = [page1, page2]

        src = NotionSource(token="tok")
        blocks = src._fetch_all_blocks("pg-1")

        assert len(blocks) == 2
        assert mock_get.call_count == 2
        # the second request must carry the cursor from the first page
        second_url = mock_get.call_args_list[1].args[0]
        assert "start_cursor=cur-2" in second_url


# ---------------------------------------------------------------------------
# NotionSource.fetch_database_as_table
# ---------------------------------------------------------------------------


class TestFetchDatabaseAsTable:
    @patch("video_processor.sources.notion_source.requests.post")
    @patch("video_processor.sources.notion_source.requests.get")
    def test_builds_sorted_csv_across_pages(self, mock_get, mock_post):
        schema = MagicMock()
        schema.raise_for_status.return_value = None
        schema.json.return_value = {
            "properties": {
                "Name": {"type": "title"},
                "Age": {"type": "number"},
            }
        }
        mock_get.return_value = schema

        page1 = MagicMock()
        page1.raise_for_status.return_value = None
        page1.json.return_value = {
            "results": [
                {
                    "properties": {
                        "Name": {
                            "type": "title",
                            "title": [{"plain_text": "Alice"}],
                        },
                        "Age": {"type": "number", "number": 30},
                    }
                }
            ],
            "has_more": True,
            "next_cursor": "c2",
        }
        page2 = MagicMock()
        page2.raise_for_status.return_value = None
        page2.json.return_value = {
            "results": [
                {
                    "properties": {
                        "Name": {"type": "title", "title": [{"plain_text": "Bob"}]},
                        "Age": {"type": "number", "number": 25},
                    }
                },
                {
                    # Carol has no Age property — the missing column renders empty
                    "properties": {
                        "Name": {"type": "title", "title": [{"plain_text": "Carol"}]},
                    }
                },
            ],
            "has_more": False,
            "next_cursor": None,
        }
        mock_post.side_effect = [page1, page2]

        src = NotionSource(token="tok")
        table = src.fetch_database_as_table("db-1")
        lines = table.split("\n")

        # columns are sorted alphabetically: Age before Name
        assert lines[0] == "Age,Name"
        assert lines[1] == "30,Alice"
        assert lines[2] == "25,Bob"
        assert lines[3] == ",Carol"
        assert mock_post.call_count == 2
        assert mock_post.call_args_list[1].kwargs["json"] == {"start_cursor": "c2"}
