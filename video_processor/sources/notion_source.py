"""Notion API source connector for fetching pages and databases."""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import requests

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)

NOTION_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"


class NotionSource(BaseSource):
    """
    Fetch pages and databases from Notion via the public API.

    Requires a Notion integration token (internal integration).
    Set NOTION_API_KEY env var or pass token directly.

    Requires: pip install requests
    """

    def __init__(
        self,
        token: Optional[str] = None,
        database_id: Optional[str] = None,
        page_ids: Optional[List[str]] = None,
    ):
        self.token = token or os.environ.get("NOTION_API_KEY", "")
        self.database_id = database_id
        self.page_ids = page_ids or []

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def authenticate(self) -> bool:
        """Check token is set and make a test call to the Notion API."""
        if not self.token:
            logger.error("Notion token not set. Provide token or set NOTION_API_KEY.")
            return False
        try:
            resp = requests.get(
                f"{NOTION_BASE_URL}/users/me",
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            user = resp.json()
            logger.info("Authenticated with Notion as %s", user.get("name", "unknown"))
            return True
        except requests.RequestException as exc:
            logger.error("Notion authentication failed: %s", exc)
            return False

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """List Notion pages as SourceFiles.

        If database_id is set, query the database for pages.
        If page_ids is set, fetch each page individually.
        """
        files: List[SourceFile] = []

        if self.database_id:
            files.extend(self._list_from_database(self.database_id))

        if self.page_ids:
            files.extend(self._list_from_pages(self.page_ids))

        if not files:
            logger.warning("No pages found. Set database_id or page_ids.")

        return files

    def _list_from_database(self, database_id: str) -> List[SourceFile]:
        """Query a Notion database and return SourceFiles for each row."""
        files: List[SourceFile] = []
        has_more = True
        start_cursor: Optional[str] = None

        while has_more:
            body: Dict = {}
            if start_cursor:
                body["start_cursor"] = start_cursor

            resp = requests.post(
                f"{NOTION_BASE_URL}/databases/{database_id}/query",
                headers=self._headers(),
                json=body,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            for page in data.get("results", []):
                title = _extract_page_title(page)
                files.append(
                    SourceFile(
                        name=title,
                        id=page["id"],
                        mime_type="text/markdown",
                        modified_at=page.get("last_edited_time"),
                    )
                )

            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        return files

    def _list_from_pages(self, page_ids: List[str]) -> List[SourceFile]:
        """Fetch individual pages by ID and return SourceFiles."""
        files: List[SourceFile] = []
        for page_id in page_ids:
            try:
                resp = requests.get(
                    f"{NOTION_BASE_URL}/pages/{page_id}",
                    headers=self._headers(),
                    timeout=15,
                )
                resp.raise_for_status()
                page = resp.json()
                title = _extract_page_title(page)
                files.append(
                    SourceFile(
                        name=title,
                        id=page["id"],
                        mime_type="text/markdown",
                        modified_at=page.get("last_edited_time"),
                    )
                )
            except requests.RequestException as exc:
                logger.error("Failed to fetch page %s: %s", page_id, exc)
        return files

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download page blocks as markdown text and save to destination."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        blocks = self._fetch_all_blocks(file.id)
        text = self._blocks_to_text(blocks)

        # Prepend title
        content = f"# {file.name}\n\n{text}"
        destination.write_text(content, encoding="utf-8")
        logger.info("Saved Notion page to %s", destination)
        return destination

    def _fetch_all_blocks(self, page_id: str) -> list:
        """Fetch all child blocks for a page, handling pagination."""
        blocks: list = []
        has_more = True
        start_cursor: Optional[str] = None

        while has_more:
            url = f"{NOTION_BASE_URL}/blocks/{page_id}/children?page_size=100"
            if start_cursor:
                url += f"&start_cursor={start_cursor}"

            resp = requests.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()

            blocks.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        return blocks

    def _blocks_to_text(self, blocks: list) -> str:
        """Convert Notion block objects to markdown text."""
        lines: List[str] = []
        numbered_index = 0

        for block in blocks:
            block_type = block.get("type", "")
            block_data = block.get(block_type, {})

            if block_type == "paragraph":
                text = _rich_text_to_str(block_data.get("rich_text", []))
                lines.append(text)
                numbered_index = 0

            elif block_type == "heading_1":
                text = _rich_text_to_str(block_data.get("rich_text", []))
                lines.append(f"# {text}")
                numbered_index = 0

            elif block_type == "heading_2":
                text = _rich_text_to_str(block_data.get("rich_text", []))
                lines.append(f"## {text}")
                numbered_index = 0

            elif block_type == "heading_3":
                text = _rich_text_to_str(block_data.get("rich_text", []))
                lines.append(f"### {text}")
                numbered_index = 0

            elif block_type == "bulleted_list_item":
                text = _rich_text_to_str(block_data.get("rich_text", []))
                lines.append(f"- {text}")
                numbered_index = 0

            elif block_type == "numbered_list_item":
                numbered_index += 1
                text = _rich_text_to_str(block_data.get("rich_text", []))
                lines.append(f"{numbered_index}. {text}")

            elif block_type == "to_do":
                text = _rich_text_to_str(block_data.get("rich_text", []))
                checked = block_data.get("checked", False)
                marker = "[x]" if checked else "[ ]"
                lines.append(f"- {marker} {text}")
                numbered_index = 0

            elif block_type == "code":
                text = _rich_text_to_str(block_data.get("rich_text", []))
                language = block_data.get("language", "")
                lines.append(f"```{language}")
                lines.append(text)
                lines.append("```")
                numbered_index = 0

            elif block_type == "quote":
                text = _rich_text_to_str(block_data.get("rich_text", []))
                lines.append(f"> {text}")
                numbered_index = 0

            elif block_type == "callout":
                text = _rich_text_to_str(block_data.get("rich_text", []))
                icon = block_data.get("icon", {})
                emoji = icon.get("emoji", "") if icon else ""
                prefix = f"{emoji} " if emoji else ""
                lines.append(f"> {prefix}{text}")
                numbered_index = 0

            elif block_type == "toggle":
                text = _rich_text_to_str(block_data.get("rich_text", []))
                lines.append(f"<details><summary>{text}</summary></details>")
                numbered_index = 0

            elif block_type == "divider":
                lines.append("---")
                numbered_index = 0

            else:
                # Unsupported block type — try to extract any rich_text
                text = _rich_text_to_str(block_data.get("rich_text", []))
                if text:
                    lines.append(text)
                numbered_index = 0

        return "\n\n".join(lines)

    def fetch_database_as_table(self, database_id: str) -> str:
        """Fetch a Notion database and return its rows as CSV-like text.

        Each row is a page in the database. Columns are derived from
        the database properties.
        """
        # First, get database schema for column order
        resp = requests.get(
            f"{NOTION_BASE_URL}/databases/{database_id}",
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        db_meta = resp.json()
        properties = db_meta.get("properties", {})
        columns = sorted(properties.keys())

        # Query all rows
        rows: List[Dict] = []
        has_more = True
        start_cursor: Optional[str] = None

        while has_more:
            body: Dict = {}
            if start_cursor:
                body["start_cursor"] = start_cursor

            resp = requests.post(
                f"{NOTION_BASE_URL}/databases/{database_id}/query",
                headers=self._headers(),
                json=body,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            rows.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        # Build CSV-like output
        lines: List[str] = []
        lines.append(",".join(columns))

        for row in rows:
            row_props = row.get("properties", {})
            values: List[str] = []
            for col in columns:
                prop = row_props.get(col, {})
                values.append(_extract_property_value(prop))
            lines.append(",".join(values))

        return "\n".join(lines)


def _rich_text_to_str(rich_text: list) -> str:
    """Extract plain text from a Notion rich_text array."""
    return "".join(item.get("plain_text", "") for item in rich_text)


def _extract_page_title(page: dict) -> str:
    """Extract the title from a Notion page object."""
    properties = page.get("properties", {})
    for prop in properties.values():
        if prop.get("type") == "title":
            return _rich_text_to_str(prop.get("title", []))
    return "Untitled"


def _extract_property_value(prop: dict) -> str:
    """Extract a display string from a Notion property value."""
    prop_type = prop.get("type", "")

    if prop_type == "title":
        return _rich_text_to_str(prop.get("title", []))
    elif prop_type == "rich_text":
        return _rich_text_to_str(prop.get("rich_text", []))
    elif prop_type == "number":
        val = prop.get("number")
        return str(val) if val is not None else ""
    elif prop_type == "select":
        sel = prop.get("select")
        return sel.get("name", "") if sel else ""
    elif prop_type == "multi_select":
        return "; ".join(s.get("name", "") for s in prop.get("multi_select", []))
    elif prop_type == "date":
        date = prop.get("date")
        if date:
            start = date.get("start", "")
            end = date.get("end", "")
            return f"{start} - {end}" if end else start
        return ""
    elif prop_type == "checkbox":
        return str(prop.get("checkbox", False))
    elif prop_type == "url":
        return prop.get("url", "") or ""
    elif prop_type == "email":
        return prop.get("email", "") or ""
    elif prop_type == "phone_number":
        return prop.get("phone_number", "") or ""
    elif prop_type == "status":
        status = prop.get("status")
        return status.get("name", "") if status else ""
    elif prop_type == "people":
        return "; ".join(p.get("name", "") for p in prop.get("people", []))
    elif prop_type == "relation":
        return "; ".join(r.get("id", "") for r in prop.get("relation", []))
    elif prop_type == "formula":
        formula = prop.get("formula", {})
        f_type = formula.get("type", "")
        return str(formula.get(f_type, ""))
    else:
        return ""
