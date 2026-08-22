"""Optional native PDF text extraction."""

from __future__ import annotations

import io
from dataclasses import dataclass


@dataclass(frozen=True)
class PdfPageText:
    page: int
    text: str


def extract_pdf_text(data: bytes) -> tuple[PdfPageText, ...]:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError("pypdf is not installed; tyre-bank extraction is unavailable") from error

    reader = PdfReader(io.BytesIO(data))
    pages: list[PdfPageText] = []
    for index, page in enumerate(reader.pages):
        value = (page.extract_text() or "").strip()
        pages.append(PdfPageText(index, value))
    return tuple(pages)

