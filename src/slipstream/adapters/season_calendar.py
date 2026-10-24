"""Optional championship-round metadata from the public Jolpica calendar."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class SeasonRound:
    number: int
    race_date: str


def utc_date(value: object) -> str | None:
    try:
        stamp = datetime.fromisoformat(str(value))
        if stamp.tzinfo is None:
            return None
        return stamp.astimezone(UTC).date().isoformat()
    except (TypeError, ValueError):
        return None


def fetch_season_rounds(year: int, *, opener: Any = urlopen) -> list[SeasonRound]:
    """One bounded metadata request; callers retain date ordering on failure."""
    request = Request(
        f"https://api.jolpi.ca/ergast/f1/{int(year)}/races.json?limit=100",
        headers={"User-Agent": "slipstream-f1/0.1", "Accept": "application/json"},
    )
    with opener(request, timeout=8) as response:
        payload = json.loads(response.read(1_000_001))
    rows = payload["MRData"]["RaceTable"]["Races"]
    rounds = []
    for row in rows:
        try:
            if not str(row["round"]).isdigit():
                continue
            number = int(row["round"])
            if str(row["season"]) != str(year) or not 1 <= number <= 100:
                continue
            race_date = utc_date(f"{row['date']}T{row.get('time') or '00:00:00Z'}")
            if race_date and race_date.startswith(f"{year}-"):
                rounds.append(SeasonRound(number, race_date))
        except (KeyError, TypeError, ValueError):
            continue
    dates = Counter(item.race_date for item in rounds)
    numbers = Counter(item.number for item in rounds)
    return [
        item for item in rounds if dates[item.race_date] == numbers[item.number] == 1
    ]
