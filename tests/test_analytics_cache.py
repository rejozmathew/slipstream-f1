from datetime import UTC, datetime
from pathlib import Path

import pytest

from slipstream.analytics import AnalyticsService
from slipstream.library import ReplayLibrary
from slipstream.pirelli.contracts import (
    Compound,
    PitWindow,
    StrategyOption,
    StrategyRank,
)
from slipstream.pirelli.snapshot import PirelliEvidenceSnapshot, StrategyReleaseView
from slipstream.pirelli.store import PirelliAvailability
from slipstream.weekend import ContextAvailability


@pytest.mark.parametrize("pending_status", ["FETCHING", "RETRYING"])
def test_cached_analytics_tracks_availability_with_unchanged_releases(pending_status):
    resource = ReplayLibrary(
        Path(__file__).parent / "fixtures" / "replays" / "sample-session.json"
    ).get()
    published = datetime(2026, 5, 2, 20, tzinfo=UTC)
    evidence = PirelliEvidenceSnapshot(
        release_ids=("complete-release",),
        compound_selections=(),
        strategy_releases=(
            StrategyReleaseView(
                release_id="complete-release",
                source_url="https://press.pirelli.com/strategy",
                published_at=published,
                retrieved_at=published,
                strategies=(
                    StrategyOption(
                        id="complete-strategy",
                        rank=StrategyRank.FASTEST_PUBLISHED,
                        stop_count=1,
                        compounds=(Compound.MEDIUM, Compound.HARD),
                        pit_windows=(PitWindow(22, 28),),
                    ),
                ),
            ),
        ),
        tyre_bank_snapshots=(),
        context_facts=(),
    )
    service = AnalyticsService()

    # The worker can finish writing its release before reporting completion.
    # Hold the release and replay cursor fixed while availability changes.
    # Check the reverse transition too, so cached PRESENT data cannot leak.
    for status in (pending_status, "PRESENT", pending_status):
        result = service.snapshot(
            resource,
            resource.final_state,
            sequence=len(resource.events),
            as_of=resource.final_state.updated_at,
            context=ContextAvailability("missing"),
            pirelli=PirelliAvailability(status, evidence),
        )
        for baseline in (
            result["officialPreRace"],
            result["publishedStrategy"]["baseline"],
        ):
            assert baseline["status"] == status
            if status == "PRESENT":
                assert len(baseline["options"]) == 1
                assert baseline["options"][0]["id"] == "complete-strategy"
                assert baseline["options"][0]["compounds"] == ["MEDIUM", "HARD"]
                assert baseline["options"][0]["pitWindows"] == [
                    {"startLap": 22, "endLap": 28}
                ]
            else:
                assert baseline["options"] == []
                assert baseline["contextFacts"] == []
