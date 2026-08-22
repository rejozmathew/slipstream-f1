"""Shared extractor input/output helpers."""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import ArtifactVersion


@dataclass(frozen=True)
class ArtifactInput:
    artifact: ArtifactVersion
    body: bytes
    text: str | None = None


@dataclass(frozen=True)
class HtmlDocument:
    title: str
    article_text: str
    published_at_text: str | None
    modified_at_text: str | None
    links: tuple[tuple[str, str, str | None], ...]
    tables: tuple[tuple[tuple[str, ...], ...], ...]
