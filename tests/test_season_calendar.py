"""Calendar numbering stays source-backed and optional to replay discovery."""

import io
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from slipstream.adapters.season_calendar import SeasonRound, fetch_season_rounds
from slipstream.catalog import CATALOG_FORMAT, _attach_round_numbers, sync_catalog
from slipstream.library import ReplayLibrary, _attach_local_recording


def test_calendar_parses_utc_dates_and_rejects_ambiguous_rounds():
    rows = [
        {
            "season": "2026",
            "round": "21",
            "date": "2026-11-21",
            "time": "22:00:00-08:00",
        },
        {"season": "2026", "round": "22", "date": "2026-11-29"},
        {"season": "2025", "round": "1", "date": "2025-03-01"},
        {"season": "2026", "round": "bad", "date": "2026-03-01"},
        {"season": "2026", "round": "2", "date": "2026-03-15"},
        {"season": "2026", "round": "2", "date": "2026-03-16"},
        {"season": "2026", "round": "3", "date": "2026-03-29"},
        {"season": "2026", "round": "4", "date": "2026-03-29"},
    ]

    def opener(request, timeout):
        assert (
            request.full_url
            == "https://api.jolpi.ca/ergast/f1/2026/races.json?limit=100"
        )
        assert timeout == 8
        return io.BytesIO(
            json.dumps({"MRData": {"RaceTable": {"Races": rows}}}).encode()
        )

    assert fetch_season_rounds(2026, opener=opener) == [
        SeasonRound(21, "2026-11-22"),
        SeasonRound(22, "2026-11-29"),
    ]


def race(key, date, **changes):
    return {
        "session_key": f"{key}-race",
        "meeting_key": key,
        "year": 2026,
        "session_type": "Race",
        "session_name": "Race",
        "date_start": date,
        "date_end": date,
        **changes,
    }


def test_round_match_uses_race_date_not_name_key_or_completion():
    meetings = {
        key: {"meeting_name": "Same name"} for key in ["old", "new", "future", "sprint"]
    }
    meetings["old"]["is_cancelled"] = True
    sessions = [
        race("future", "2026-11-21T22:00:00-08:00"),
        race("old", "2026-04-12T12:00:00Z"),
        race("new", "2026-10-04T07:00:00Z"),
        race("sprint", "2026-03-15T12:00:00Z", session_name="Sprint"),
    ]
    _attach_round_numbers(
        meetings,
        sessions,
        2026,
        [
            SeasonRound(16, "2026-10-04"),
            SeasonRound(21, "2026-11-22"),
            SeasonRound(4, "2026-04-12"),
            SeasonRound(2, "2026-03-15"),
        ],
    )
    assert meetings["new"]["round_number"] == 16
    assert meetings["future"]["round_number"] == 21
    assert "round_number" not in meetings["old"]
    assert "round_number" not in meetings["sprint"]


def test_ambiguous_or_cancelled_races_never_get_a_round():
    meetings = {key: {} for key in ["a", "b", "cancelled", "undated"]}
    sessions = [
        race("a", "2026-03-08T12:00:00Z"),
        race("b", "2026-03-08T15:00:00Z"),
        race("cancelled", "2026-03-15T12:00:00Z", is_cancelled=True),
        race("undated", ""),
    ]
    _attach_round_numbers(
        meetings,
        sessions,
        2026,
        [SeasonRound(1, "2026-03-08"), SeasonRound(2, "2026-03-15")],
    )
    assert all("round_number" not in item for item in meetings.values())


class CalendarSource:
    def get(self, endpoint, **kwargs):
        if endpoint == "meetings":
            return [
                {"meeting_key": "one", "meeting_name": "First GP", "year": 2026},
                {
                    "meeting_key": "cancelled",
                    "meeting_name": "Cancelled GP",
                    "year": 2026,
                    "is_cancelled": True,
                },
            ]
        return [
            race("one", "2026-03-08T12:00:00Z"),
            race(
                "one",
                "2026-03-06T12:00:00Z",
                session_key="practice",
                session_type="Practice",
                session_name="Practice 1",
            ),
            race("cancelled", "2026-04-12T12:00:00Z", is_cancelled=True),
        ]


def test_round_metadata_reaches_every_session_and_survives_local_replay_overlay(
    tmp_path,
):
    path = tmp_path / "catalog.json"
    result = sync_catalog(
        path,
        [2026],
        client=CalendarSource(),
        fetch_rounds=lambda _: [SeasonRound(1, "2026-03-08")],
    )
    assert result["round_metadata_version"] == 1
    assert result["meetings"]["cancelled"]["is_cancelled"] is True
    sessions = ReplayLibrary(tmp_path).catalog()["sessions"]
    assert [
        item["roundNumber"] for item in sessions if item["meetingKey"] == "one"
    ] == [1, 1]
    cancelled = next(item for item in sessions if item["meetingKey"] == "cancelled")
    assert cancelled["isCancelled"] is True
    assert "roundNumber" not in cancelled
    # Actual recording attachment must retain the catalog's calendar fields.
    library = ReplayLibrary(tmp_path)
    descriptor = library.descriptors["one-race"]
    local = replace(
        descriptor, round_number=None, is_cancelled=None, path=tmp_path / "race.json"
    )
    assert _attach_local_recording(descriptor, local).round_number == 1


def test_calendar_failure_still_refreshes_sessions_without_stale_numbering(tmp_path):
    path = tmp_path / "catalog.json"
    first = datetime(2026, 3, 1, tzinfo=UTC)
    sync_catalog(
        path,
        [2026],
        client=CalendarSource(),
        now=first,
        fetch_rounds=lambda _: [SeasonRound(1, "2026-03-08")],
    )

    def unavailable(_):
        raise TimeoutError("synthetic calendar unavailable")

    result = sync_catalog(
        path,
        [2026],
        client=CalendarSource(),
        now=first + timedelta(days=2),
        fetch_rounds=unavailable,
    )
    assert len(result["sessions"]) == 3
    assert "round_number" not in result["meetings"]["one"]
    assert result["meetings"]["cancelled"]["is_cancelled"] is True


def test_old_catalog_gets_one_metadata_upgrade_even_if_recent(tmp_path):
    path = tmp_path / "catalog.json"
    now = datetime(2026, 3, 1, tzinfo=UTC)
    path.write_text(
        json.dumps(
            {
                "format": CATALOG_FORMAT,
                "years": [2026],
                "updated_at": now.isoformat(),
                "sessions": [],
                "meetings": {},
            }
        )
    )
    calls = []

    def fetch(year):
        calls.append(year)
        return [SeasonRound(1, "2026-03-08")]

    for _ in range(2):
        result = sync_catalog(
            path, [2026], client=CalendarSource(), now=now, fetch_rounds=fetch
        )
        assert result["meetings"]["one"]["round_number"] == 1
    assert calls == [2026]
