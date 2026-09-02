"""Conservative event-aware discovery for the public Pirelli Formula 1 newsroom."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import quote_plus, urlparse
from xml.etree import ElementTree

from .acquisition import _parse_dt
from .contracts import ExtractionStatus
from .extractors.base import HtmlDocument

PIRELLI_F1_RSS_URL = "https://press.pirelli.com/tagfeed/en/tags/formula__1"
PIRELLI_TAGFEED_ROOT = "https://press.pirelli.com/tagfeed/en/tags/"
PIRELLI_EVENT_ARCHIVE_URL = "https://press.pirelli.com/"


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
    tag_aliases: tuple[str, ...] = ()


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


def pirelli_event_archive_url(target: MeetingDiscoveryTarget) -> str:
    tag = pirelli_event_tags(target)[0]
    return f"{PIRELLI_EVENT_ARCHIVE_URL}?h=1&t={quote_plus(tag)}"


def pirelli_event_archive_urls(target: MeetingDiscoveryTarget) -> tuple[str, ...]:
    return tuple(
        f"{PIRELLI_EVENT_ARCHIVE_URL}?h=1&t={quote_plus(tag)}"
        for tag in pirelli_event_tags(target)
    )


def pirelli_event_tags(target: MeetingDiscoveryTarget) -> tuple[str, ...]:
    primary = target.exact_tag or pirelli_event_tag(
        target.season, target.canonical_name
    )
    return tuple(dict.fromkeys((primary, *target.tag_aliases)))


def pirelli_event_rss_url(tag: str) -> str:
    """Return the bounded official PressPage feed for one exact event tag."""

    slug = re.sub(r"\s+", "__", tag.strip().casefold())
    return f"{PIRELLI_TAGFEED_ROOT}{slug}"


def entries_from_event_feed(xml_text: str, tag: str) -> tuple[FeedEntry, ...]:
    """Parse an exact-tag feed and preserve the tag as discovery scope."""

    return tuple(
        FeedEntry(
            entry.title,
            entry.url,
            entry.published_at,
            tuple(dict.fromkeys((*entry.categories, tag))),
            entry.summary,
        )
        for entry in parse_formula1_feed(xml_text)
    )


def entries_from_event_archive(
    document: HtmlDocument, target: MeetingDiscoveryTarget
) -> tuple[FeedEntry, ...]:
    """Turn one exact-event archive result page into conservatively scoped entries."""

    exact_tag = target.exact_tag or pirelli_event_tag(
        target.season, target.canonical_name
    )
    entries: list[FeedEntry] = []
    seen: set[str] = set()
    scoped_archive_links = bool(document.archive_links)
    aliases = tuple(
        {
            target.canonical_name.casefold(),
            *(alias.casefold() for alias in target.aliases),
        }
    )
    for url, label, _media_type in document.archive_links or document.links:
        parsed = urlparse(url)
        title = label.strip()
        if parsed.hostname != "press.pirelli.com" or not title:
            continue
        if url in seen or parsed.path in {"", "/"} or parsed.query or parsed.fragment:
            continue
        # The newsroom's text_latestnews_more links are the result cards on this
        # exact event-tag archive. Their article titles/slugs need not repeat the
        # canonical meeting name or season (for example, "Zandvoort"). Synthetic
        # or legacy documents without structural card data retain the old
        # conservative name + season fallback.
        if not scoped_archive_links:
            if not any(alias and alias in title.casefold() for alias in aliases):
                continue
            if str(target.season) not in f"{title} {url}":
                continue
        seen.add(url)
        entries.append(
            FeedEntry(
                title=title,
                url=url,
                published_at=None,
                categories=(exact_tag,),
                summary=f"Official Pirelli event archive result for {exact_tag}",
            )
        )
    return tuple(entries)


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
                # PressPage's production Formula 1 feed serializes its complete
                # tag list in one comma-separated category element.  Preserve
                # normal RSS category elements while exposing each real tag to
                # exact-event matching.
                categories.extend(
                    category.strip() for category in text.split(",") if category.strip()
                )
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
            r"\b(?:fastest|quickest)(?: option)? for tomorrow\b",
            sentence,
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
        "sprint" in segment and any(word in segment for word in ("pole", "qualifying"))
        for segment in segments
    )


def classify_release_purpose(title: str, summary: str = "") -> ReleasePurpose:
    title_lower = title.casefold()
    lower = f"{title} {summary}".casefold()
    race_guidance_title = any(
        marker in title_lower
        for marker in ("race strateg", "for the race", "grand prix strategy")
    )
    ranked_stop_strategy = re.search(
        r"\b(?:fastest|quickest|best)\s+strateg(?:y|ies)\b[^.]{0,100}"
        r"\b(?:one|two|three)[ -]stop\b",
        lower,
    )
    if race_guidance_title and (_explicit_race_strategy(lower) or ranked_stop_strategy):
        return ReleasePurpose.RACE_STRATEGY
    if ranked_stop_strategy and any(
        marker in lower
        for marker in ("grand prix", "remainder of the race", "complete the race")
    ):
        return ReleasePurpose.RACE_STRATEGY
    # An explicitly Sprint-strategy title scopes an otherwise ambiguous "tomorrow"
    # sentence to the Sprint. A Sprint result recap (as in the Miami release) does
    # not trigger this veto, so stronger prospective Grand Prix guidance still wins.
    if _explicit_sprint_strategy(title_lower):
        return ReleasePurpose.SPRINT
    # A single official release can recap Sprint/Qualifying before giving explicit
    # prospective Grand Prix guidance. That sentence-local Race evidence is stronger
    # than incidental nomination wording elsewhere in the article.
    if _explicit_race_strategy(lower):
        return ReleasePurpose.RACE_STRATEGY
    if "compound" in lower and any(
        word in lower for word in ("selected", "selection", "choices")
    ):
        return ReleasePurpose.COMPOUND_NOMINATION
    if any(word in title_lower for word in ("friday", "practice", "fp1", "fp2", "fp3")):
        return ReleasePurpose.PRACTICE
    if any(
        marker in title_lower for marker in ("last year", "previous race", "history of")
    ):
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
        if any(tag.casefold() in categories for tag in pirelli_event_tags(target)):
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
