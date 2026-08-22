"""Public Pirelli artifact acquisition. Raw bytes are archived before extraction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import aiohttp

from .archive import PirelliArchive
from .contracts import ArtifactVersion, SourceType
from .extractors.html import parse_html

_ALLOWED_HOSTS = {"press.pirelli.com", "content.presspage.com"}
COLLECTOR_VERSION = "slipstream-pirelli-v5.0.0"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _source_type(media_type: str, url: str) -> SourceType:
    lower = media_type.casefold()
    if "html" in lower:
        return SourceType.NEWSROOM_HTML
    if "pdf" in lower or url.casefold().endswith(".pdf"):
        return SourceType.PDF
    if lower.startswith("image/"):
        return SourceType.IMAGE
    if "xml" in lower or "rss" in lower:
        return SourceType.RSS
    return SourceType.OTHER


def _extension(source_type: SourceType, media_type: str) -> str:
    if source_type == SourceType.NEWSROOM_HTML:
        return "html"
    if source_type == SourceType.PDF:
        return "pdf"
    if source_type == SourceType.RSS:
        return "xml"
    if source_type == SourceType.IMAGE:
        return {"image/png": "png", "image/webp": "webp"}.get(media_type, "jpg")
    return "bin"


@dataclass(frozen=True)
class AcquiredArtifact:
    artifact: ArtifactVersion
    body: bytes


class PirelliPublicClient:
    def __init__(self, *, timeout_seconds: float = 20.0, max_bytes: int = 8_000_000, attempts: int = 3) -> None:
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.max_bytes = max_bytes
        self.attempts = max(1, attempts)
        self.headers = {
            "User-Agent": "SlipstreamF1-PirelliIngest/5",
            "Accept": "text/html,application/pdf,image/*,application/xml;q=0.9,*/*;q=0.1",
        }

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
            raise ValueError(f"unsupported Pirelli artifact host: {url}")

    async def _fetch(self, url: str) -> tuple[str, bytes, str]:
        import asyncio

        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                async with aiohttp.ClientSession(timeout=self.timeout, headers=self.headers) as session:
                    async with session.get(url, allow_redirects=True) as response:
                        response.raise_for_status()
                        final_url = str(response.url)
                        self._validate_url(final_url)
                        body = await response.content.read(self.max_bytes + 1)
                        if len(body) > self.max_bytes:
                            raise ValueError(f"Pirelli artifact exceeds {self.max_bytes} bytes")
                        media_type = response.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0].casefold()
                        return final_url, body, media_type
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
                last_error = error
                if attempt + 1 < self.attempts:
                    await asyncio.sleep(0.5 * (2 ** attempt))
        if last_error is not None:
            raise last_error
        raise RuntimeError("Pirelli fetch failed without an error")

    async def fetch_public(self, url: str) -> tuple[str, bytes, str]:
        """Fetch one allowlisted public Pirelli artifact with bounded retry/backoff."""
        self._validate_url(url)
        return await self._fetch(url)

    async def acquire(
        self,
        *,
        archive: PirelliArchive,
        meeting_key: str,
        url: str,
        now: datetime | None = None,
    ) -> AcquiredArtifact:
        self._validate_url(url)
        retrieved = now or datetime.now(timezone.utc)
        final_url, body, media_type = await self._fetch(url)

        stype = _source_type(media_type, final_url)
        published: datetime | None = None
        modified: datetime | None = None
        if stype == SourceType.NEWSROOM_HTML:
            doc = parse_html(body.decode("utf-8", errors="replace"), final_url)
            published = _parse_dt(doc.published_at_text)
            modified = _parse_dt(doc.modified_at_text)

        artifact = archive.archive_artifact(
            meeting_key=meeting_key,
            source_url=final_url,
            source_type=stype,
            body=body,
            retrieved_at=retrieved,
            published_at=published,
            modified_at=modified,
            media_type=media_type,
            collector_version=COLLECTOR_VERSION,
            extension=_extension(stype, media_type),
        )
        return AcquiredArtifact(artifact, body)

