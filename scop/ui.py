from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from scop.models.protocol import MSGID


def parse_ndjson(text: str) -> list[dict[str, Any]]:
    """Parse NDJSON text into event dicts, silently skipping malformed lines."""
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


@dataclass
class UIPage:
    key: str
    title: str
    scalars: dict[str, dict[str, Any]] = field(default_factory=dict)
    lists: dict[str, dict[str, Any]] = field(default_factory=dict)
    tables: dict[str, dict[str, Any]] = field(default_factory=dict)


class UIModel:
    """State-only model: tracks page slots from SCOP events.

    No dispatch calls, no rendering decisions.  Feed events in; read slots out.
    """

    def __init__(self) -> None:
        self.pages: dict[str, UIPage] = {}
        self.active_page: str | None = None

    def ingest(self, event: dict[str, Any]) -> None:
        msgid = str(event.get("msgid", ""))

        if msgid == MSGID.PAGE_BEGIN:
            page_id = str(event.get("id", "")).strip()
            if page_id and page_id not in self.pages:
                self.pages[page_id] = UIPage(
                    key=page_id,
                    title=str(event.get("label") or page_id),
                )
            if self.active_page is None and page_id:
                self.active_page = page_id
            return

        page = self.pages.get(self.active_page or "")
        if page is None:
            return

        if msgid == MSGID.SCALAR_SET:
            sid = str(event.get("id", ""))
            if sid:
                page.scalars[sid] = event

        elif msgid == MSGID.LIST_DECLARE:
            lid = str(event.get("id", ""))
            if lid and lid not in page.lists:
                page.lists[lid] = {"declare": event, "items": []}

        elif msgid == MSGID.LIST_APPEND:
            lid = str(event.get("id", ""))
            entry = page.lists.get(lid)
            if entry is not None:
                items = entry.get("items")
                if isinstance(items, list):
                    items.append(event.get("value"))

        elif msgid == MSGID.TABLE_DECLARE:
            tid = str(event.get("id", ""))
            if tid and tid not in page.tables:
                page.tables[tid] = {"declare": event, "rows": []}

        elif msgid == MSGID.TABLE_ROW:
            tid = str(event.get("id", ""))
            entry = page.tables.get(tid)
            if entry is not None:
                values = event.get("values")
                if isinstance(values, dict):
                    rows = entry.get("rows")
                    if isinstance(rows, list):
                        rows.append({str(k): str(v) for k, v in values.items()})

    def ingest_many(self, events: list[dict[str, Any]]) -> None:
        for ev in events:
            self.ingest(ev)

    def current_page(self) -> UIPage | None:
        if self.active_page is None:
            return None
        return self.pages.get(self.active_page)


__all__ = ["UIModel", "UIPage", "parse_ndjson"]
