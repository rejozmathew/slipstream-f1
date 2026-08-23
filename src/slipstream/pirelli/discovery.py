"""Conservative event-aware discovery for the public Pirelli Formula 1 newsroom."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlparse
from xml.etree import ElementTree

from .acquisition import _parse_dt
from .contracts import ExtractionStatus
from .extractors.base import HtmlDocument

PIRELLI_F1_RSS_URL = "https://press.pirelli.com/tagfeed/en/tags/formula__1"


class ReleasePurpose(StrEnum):
    COMPOUND_NOMINATION = "COMPOUND_NOMINATION"
    PREVIEW = "PREVIEW"
    PRACTICE = "PRACTICE"
    SPRINT_QUALIFYING = "SPRINT_QUALIFYING"
    SPRINT = "SPRINT"
    RACE_STRATEGY = "RACE_STRATEGY"
    QUALIFYING_STRATEGY = "QUALIFYING_STRATEGY"
    RACE_REPORT = "RACE_REPORT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class MeetingDiscoveryTarget:
    meeting_key: str
    canonical_name: str
    season: int
    weekend_start: datetime
    weekend_end: datetime
    aliases: tuple[str, ...] = ()
    exact_tag: str | None = None


@dataclass(frozen=True)
class FeedEntry:
    title: str
    url: str
    published_at: datetime | None
    categories: tuple[str, ...]
    summary: str


@dataclass(frozen=True)
class ReleaseCandidate:
    status: ExtractionStatus
    entry: FeedEntry
    purpose: ReleasePurpose
    match_reason: str
    score: int


@dataclass(frozen=True)
class AssetCandidate:
    status: ExtractionStatus
    url: str
    label: str
    purpose: str
    reason: str


def pirelli_event_tag(season: int, canonical_name: str) -> str:
    """Build the exact event category used by Pirelli's Formula 1 tag feed."""

    name = re.sub(r"\s+", " ", canonical_name).strip()
    prefix = f"{season} "
    return name if name.casefold().startswith(prefix.casefold()) else f"{prefix}{name}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()


def parse_formula1_feed(xml_text: str) -> tuple[FeedEntry, ...]:
    root = ElementTree.fromstring(xml_text)
    out: list[FeedEntry] = []
    for node in root.iter():
        if _local(node.tag) not in {"item", "entry"}:
            continue
        title = ""
        url = ""
        published: datetime | None = None
        categories: list[str] = []
        summary = ""
        for child in node:
            name = _local(child.tag)
            text = (child.text or "").strip()
            if name == "title":
                title = text
            elif name == "link":
                url = child.attrib.get("href", "").strip() or text
            elif name in {"pubdate", "published", "updated"} and published is None:
                published = _parse_dt(text)
            elif name == "category" and text:
                categories.append(text)
            elif name in {"description", "summary"}:
                summary = text
        if title and url:
            out.append(FeedEntry(title, url, published, tuple(categories), summary))
    return tuple(out)


def _explicit_sprint_strategy(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "sprint strategy",
            "sprint strategies",
            "strategy for the sprint",
            "strategies for the sprint",
        )
    )


def _explicit_race_strategy(text: str) -> bool:
    """Recognize current-event Grand Prix guidance, not incidental session words."""

    historical_markers = (
        "last year's",
        "last year’s",
        "previous year's",
        "previous year’s",
        "in the previous race",
        "historically",
    )
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if any(marker in sentence for marker in historical_markers):
            continue
        if any(
            phrase in sentence
            for phrase in (
                "race strategy",
                "race strategies",
                "strategy for the race",
                "strategies for the race",
                "possible race strategy",
                "possible race strategies",
            )
        ):
            return True
        if re.search(
            r"\b(?:one|two|three)[ -]stop strateg(?:y|ies)\b[^.]{0,180}"
            r"\b(?:fastest for tomorrow|for (?:tomorrow's |tomorrow’s )?(?:the )?"
            r"[a-z0-9 -]*grand prix|complete the race|pit stop window)\b",
            sentence,
        ):
            return True
    return False


def _localized_sprint_qualifying(title: str, text: str) -> bool:
    segments = (title, *re.split(r"(?<=[.!?])\s+", text))
    return any(
        "sprint" in segment
        and any(word in segment for word in ("pole", "qualifying"))
        for segment in segments
    )


def classify_release_purpose(title: str, summary: str = "") -> ReleasePurpose:
    title_lower = title.casefold()
    lower = f"{title} {summary}".casefold()
    if "compound" in lower and any(
        word in lower for word in ("selected", "selection", "choices")
    ):
        return ReleasePurpose.COMPOUND_NOMINATION
    if _explicit_sprint_strategy(title_lower):
        return ReleasePurpose.SPRINT
    if any(word in title_lower for word in ("friday", "practice", "fp1", "fp2", "fp3")):
        return ReleasePurpose.PRACTICE
    if any(marker in title_lower for marker in ("last year", "previous race", "history of")):
        return ReleasePurpose.UNKNOWN
    if any(word in title_lower for word in ("wins", "victory", "winner")):
        return (
            ReleasePurpose.SPRINT
            if "sprint" in title_lower
            else ReleasePurpose.RACE_REPORT
        )
    if _explicit_race_strategy(title_lower):
        return ReleasePurpose.RACE_STRATEGY
    # Explicit prospective Grand Prix strategy evidence outranks incidental words
    # from the earlier Sprint, F1 qualifying, or support-series boilerplate.
    if _explicit_race_strategy(lower):
        return ReleasePurpose.RACE_STRATEGY
    if _explicit_sprint_strategy(lower):
        return ReleasePurpose.SPRINT
    if _localized_sprint_qualifying(title_lower, lower):
        return ReleasePurpose.SPRINT_QUALIFYING
    if "sprint" in lower and any(
        word in lower for word in ("wins", "victory", "winner")
    ):
        return ReleasePurpose.SPRINT
    if any(word in lower for word in ("pole", "qualifying")) and any(
        word in lower for word in ("strategy", "strategies", "tyre", "tire")
    ):
        return ReleasePurpose.QUALIFYING_STRATEGY
    if any(word in lower for word in ("friday", "practice", "fp1", "fp2", "fp3")):
        return ReleasePurpose.PRACTICE
    if any(word in lower for word in ("wins", "victory", "winner")):
        return ReleasePurpose.RACE_REPORT
    if any(
        word in lower
        for word in ("grand prix", "weekend", "formula 1 resumes", "faces its")
    ):
        return ReleasePurpose.PREVIEW
    return ReleasePurpose.UNKNOWN


def discover_for_meeting(
    entries: tuple[FeedEntry, ...],
    target: MeetingDiscoveryTarget,
) -> tuple[ReleaseCandidate, ...]:
    """Return conservative candidate releases for one meeting.

    Exact event tags dominate. Alias/title matches are allowed for multi-event compound
    nomination releases. Ambiguous entries remain NEEDS_REVIEW instead of being silently
    attached to a meeting.
    """
    aliases = tuple(
        {target.canonical_name.casefold(), *(x.casefold() for x in target.aliases)}
    )
    lower_bound = target.weekend_start.astimezone(UTC) - timedelta(days=35)
    upper_bound = target.weekend_end.astimezone(UTC) + timedelta(days=2)
    out: list[ReleaseCandidate] = []
    for entry in entries:
        if entry.published_at is not None and not (
            lower_bound <= entry.published_at <= upper_bound
        ):
            continue
        title = entry.title.casefold()
        summary = entry.summary.casefold()
        categories = {value.casefold() for value in entry.categories}
        score = 0
        reasons: list[str] = []
        if target.exact_tag and target.exact_tag.casefold() in categories:
            score += 100
            reasons.append("exact_event_tag")
        title_hits = [alias for alias in aliases if alias and alias in title]
        summary_hits = [alias for alias in aliases if alias and alias in summary]
        if title_hits:
            score += 70
            reasons.append("meeting_alias_in_title")
        elif summary_hits:
            score += 40
            reasons.append("meeting_alias_in_summary")

        purpose = classify_release_purpose(entry.title, entry.summary)
        if score == 0:
            continue
        # Exact tag is authoritative. Alias-only discovery is acceptable for nomination
        # releases but still requires fact-level meeting scoping later.
        status = (
            ExtractionStatus.ACCEPTED
            if (
                "exact_event_tag" in reasons
                or (purpose == ReleasePurpose.COMPOUND_NOMINATION and bool(title_hits))
            )
            else ExtractionStatus.NEEDS_REVIEW
        )
        out.append(ReleaseCandidate(status, entry, purpose, "+".join(reasons), score))
    return tuple(
        sorted(
            out,
            key=lambda item: (
                item.entry.published_at or datetime.min.replace(tzinfo=UTC),
                item.score,
            ),
        )
    )


def discover_official_assets(document: HtmlDocument) -> tuple[AssetCandidate, ...]:
    out: list[AssetCandidate] = []
    for url, label, media_type in document.links:
        host = urlparse(url).hostname or ""
        if host not in {"press.pirelli.com", "content.presspage.com"}:
            continue
        lower = f"{label} {url}".casefold()
        if any(
            marker in lower
            for marker in (
                "tyre sets available for the race",
                "tire sets available for the race",
                "tyres available for the race",
                "tires available for the race",
                "tyre sets available",
                "tire sets available",
            )
        ):
            out.append(
                AssetCandidate(
                    ExtractionStatus.ACCEPTED,
                    url,
                    label,
                    "RACE_TYRE_BANK",
                    "explicit tyre-sets-available label",
                )
            )
        elif (media_type or "").casefold() == "application/pdf" and "tyre" in lower:
            out.append(
                AssetCandidate(
                    ExtractionStatus.NEEDS_REVIEW,
                    url,
                    label,
                    "UNKNOWN_TYRE_PDF",
                    "Pirelli tyre PDF without explicit race-availability label",
                )
            )
    return tuple(out)
