import json
from dataclasses import asdict, replace

from slipstream.analytics import _dry_tyre_state
from slipstream.events import NormalizedEvent
from slipstream.evidence import LapObservation
from slipstream.library import ReplayLibrary
from slipstream.qualifying import build_qualifying_snapshot
from slipstream.replay import replay
from slipstream.state import DriverState
from slipstream.strategy_rules import strategy_rule_profile


def test_partial_race_cannot_prove_unsatisfied_dry_requirement():
    driver = DriverState("1", lap=30, compound="HARD")
    rules = strategy_rule_profile(2026, "race")
    assert _dry_tyre_state(driver, rules, ()) == "UNKNOWN"
    observations = (LapObservation(29, "2026-07-26T13:00:00+00:00", compound="HARD"),)
    assert _dry_tyre_state(driver, rules, observations) == "UNKNOWN"
    assert _dry_tyre_state(driver, rules, observations + (replace(observations[0], compound="MEDIUM"),)) == "SATISFIED"


def test_verified_wet_tyre_use_exempts_dry_requirement_but_unknown_rule_stays_unknown():
    driver = DriverState("1", lap=1, compound="INTERMEDIATE")
    assert _dry_tyre_state(driver, strategy_rule_profile(2026, "race"), ()) == "NOT_APPLICABLE"
    assert _dry_tyre_state(driver, strategy_rule_profile(2024, "race"), ()) == "UNKNOWN"


def test_qualifying_flag_waits_for_explicit_cursor_eligible_source_completion(tmp_path):
    events = [
        NormalizedEvent("session", "2026-07-25T14:00:00+00:00", "test", {
            "key": "qual-settle", "name": "Qualifying", "session_kind": "qualifying",
            "layout_family": "qualifying", "qualifying_phase": "Q3", "status": "RUNNING",
            "started_at": "2026-07-25T14:00:00+00:00", "eligible_field_size": 22,
        }),
        NormalizedEvent("session", "2026-07-25T15:00:00+00:00", "test", {"status": "FINISHED"}),
        NormalizedEvent("session", "2026-07-25T15:02:00+00:00", "test", {"session_complete": True}),
    ]
    path = tmp_path / "qual.json"
    path.write_text(json.dumps([asdict(event) for event in events]), encoding="utf-8")
    resource = ReplayLibrary(path).get()
    at_flag = build_qualifying_snapshot(resource, replay(events[:2]), sequence=2)
    assert at_flag["final"] is True  # Legacy final-segment flag, not official final.
    assert at_flag["settlement"] == "SETTLING"
    assert at_flag["resultStatus"] == "provisional"
    complete = build_qualifying_snapshot(resource, replay(events), sequence=3)
    assert complete["settlement"] == "SOURCE_COMPLETE"
    assert complete["resultStatus"] == "provisional"
