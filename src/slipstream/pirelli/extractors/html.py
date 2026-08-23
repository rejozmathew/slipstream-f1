"""Structured HTML and metadata extraction. First preference when available."""

from __future__ import annotations

import html as html_lib
import json
import re
from collections.abc import Iterable
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

from .base import HtmlDocument


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(value or "")).strip()


class _Parser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.meta: dict[str, str] = {}
        self.jsonld: list[str] = []
        self._json = False
        self._json_chunks: list[str] = []
        self._ignore = 0
        self._article = 0
        self._article_chunks: list[str] = []
        self._link: tuple[str, str | None] | None = None
        self._link_chunks: list[str] = []
        self.links: list[tuple[str, str, str | None]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell = False
        self._cell_chunks: list[str] = []
        self.tables: list[tuple[tuple[str, ...], ...]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = {k.lower(): (v or "") for k, v in attrs}
        tag = tag.lower()
        if tag == "script":
            if d.get("type", "").casefold() == "application/ld+json":
                self._json = True
            else:
                self._ignore += 1
        elif tag in {"style", "noscript", "svg"}:
            self._ignore += 1
        if tag == "meta":
            key = (
                d.get("property") or d.get("name") or d.get("itemprop") or ""
            ).casefold()
            if key and d.get("content"):
                self.meta[key] = d["content"]
        if tag in {"article", "main"}:
            self._article += 1
        if tag == "a" and d.get("href"):
            self._link = (urljoin(self.base_url, d["href"]), d.get("type") or None)
            self._link_chunks = []
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = True
            self._cell_chunks = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script" and self._json:
            self._json = False
            if self._json_chunks:
                self.jsonld.append("".join(self._json_chunks))
                self._json_chunks.clear()
            return
        if tag in {"script", "style", "noscript", "svg"} and self._ignore:
            self._ignore -= 1
        if tag in {"article", "main"} and self._article:
            self._article -= 1
        if tag == "a" and self._link is not None:
            url, media_type = self._link
            self.links.append((url, _clean(" ".join(self._link_chunks)), media_type))
            self._link = None
            self._link_chunks = []
        if tag in {"td", "th"} and self._cell and self._row is not None:
            self._row.append(_clean(" ".join(self._cell_chunks)))
            self._cell = False
            self._cell_chunks = []
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(
                tuple(tuple(cell for cell in row) for row in self._table)
            )
            self._table = None

    def handle_data(self, data: str) -> None:
        if self._json:
            self._json_chunks.append(data)
            return
        if self._ignore:
            return
        text = _clean(data)
        if not text:
            return
        if self._article:
            self._article_chunks.append(text)
        if self._link is not None:
            self._link_chunks.append(text)
        if self._cell:
            self._cell_chunks.append(text)


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def parse_html(source: str, base_url: str) -> HtmlDocument:
    parser = _Parser(base_url)
    parser.feed(source)

    title = ""
    body = ""
    published: str | None = None
    modified: str | None = None
    for raw in parser.jsonld:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in _walk(obj):
            if not title and isinstance(node.get("headline"), str):
                title = _clean(node["headline"])
            if not body and isinstance(node.get("articleBody"), str):
                body = _clean(node["articleBody"])
            if not published and isinstance(node.get("datePublished"), str):
                published = node["datePublished"]
            if not modified and isinstance(node.get("dateModified"), str):
                modified = node["dateModified"]

    title = title or _clean(
        parser.meta.get("og:title") or parser.meta.get("twitter:title") or ""
    )
    body = body or _clean(" ".join(parser._article_chunks))
    published = (
        published
        or parser.meta.get("article:published_time")
        or parser.meta.get("datepublished")
    )
    modified = (
        modified
        or parser.meta.get("article:modified_time")
        or parser.meta.get("datemodified")
    )

    return HtmlDocument(
        title=title,
        article_text=body,
        published_at_text=published,
        modified_at_text=modified,
        links=tuple(parser.links),
        tables=tuple(parser.tables),
    )
