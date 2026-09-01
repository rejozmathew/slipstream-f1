from __future__ import annotations

from dataclasses import asdict

import pytest

from slipstream.evidence import SessionEvidence
from slipstream.f1_timing import finalize_f1_classifications
from slipstream.live import F1LiveAdapter
from slipstream.state import RaceState


def _provider_rows(name: str, session_type: str) -> list[tuple[str, dict, str]]:
    rows: list[tuple[str, dict, str]] = [
        (
            "SessionInfo",
            {"Key": 9001, "Name": name, "Type": session_type},
            "2026-08-23T13:00:00Z",
        ),
        ("SessionStatus", {"Status": "Started"}, "2026-08-23T13:00:01Z"),
        ("TrackStatus", {"Status": "1"}, "2026-08-23T13:00:02Z"),
        (
            "TimingAppData",
            {
                "Lines": {
                    "44": {
                        "Stints": {
                            "0": {
                                "Compound": "SOFT",
                                "New": "true",
                                "TotalLaps": 1,
                                "StartLaps": 0,
                            }
                        }
                    }
                }
            },
            "2026-08-23T13:00:03Z",
        ),
        (
            "TimingData",
            {
                "Lines": {
                    "44": {
                        "RacingNumber": "44",
                        "Position": "1",
                        "NumberOfLaps": 1,
                        "NumberOfPitStops": 0,
                        "InPit": False,
                        "Retired": False,
                        "Stopped": False,
                        "LastLapTime": {"Value": "1:20.000"},
                        "Sectors": {
                            "0": {"Value": "25.000"},
                            "1": {"Value": "27.000"},
                            "2": {"Value": "28.000"},
                        },
                    }
                }
            },
            "2026-08-23T13:02:00Z",
        ),
        (
            "TimingData",
            {"Lines": {"44": {"NumberOfPitStops": 1, "InPit": True}}},
            "2026-08-23T13:03:00Z",
        ),
        (
            "TimingData",
            {"Lines": {"44": {"InPit": False}}},
            "2026-08-23T13:03:20Z",
        ),
        (
            "TimingAppData",
            {
                "Lines": {
                    "44": {
                        "Stints": {
                            "1": {
                                "Compound": "HARD",
                                "New": "true",
                                "TotalLaps": 0,
                                "StartLaps": 0,
                            }
                        }
                    }
                }
            },
            "2026-08-23T13:03:21Z",
        ),
        (
            "TimingData",
            {"Lines": {"44": {"Stopped": True, "Retired": False}}},
            "2026-08-23T13:04:00Z",
        ),
        (
            "TimingData",
            {"Lines": {"44": {"Stopped": False, "Retired": False}}},
            "2026-08-23T13:04:01Z",
        ),
        (
            "TimingData",
            {"Lines": {"44": {"Stopped": True, "Retired": True}}},
            "2026-08-23T13:04:02Z",
        ),
        (
            "TimingData",
            {"Lines": {"44": {"Stopped": False, "Retired": False}}},
            "2026-08-23T13:04:03Z",
        ),
        ("TrackStatus", {"Status": "4"}, "2026-08-23T13:05:00Z"),
        ("TrackStatus", {"Status": "6"}, "2026-08-23T13:05:10Z"),
        ("SessionStatus", {"Status": "Suspended"}, "2026-08-23T13:05:20Z"),
        ("TrackStatus", {"Status": "5"}, "2026-08-23T13:05:21Z"),
        (
            "RaceControlMessages",
            {
                "Messages": {
                    "0": {
                        "Utc": "2026-08-23T13:05:30Z",
                        "Category": "Flag",
                        "Message": "TRACK CLEAR",
                        "Flag": "CLEAR",
                        "Scope": "TRACK",
                    }
                }
            },
            "2026-08-23T13:05:30Z",
        ),
        ("SessionStatus", {"Status": "Started"}, "2026-08-23T13:06:00Z"),
    ]
    if session_type == "Qualifying":
        rows.extend(
            (
                (
                    "SessionData",
                    {"Series": {str(index): {"QualifyingPart": int(phase)}}},
                    f"2026-08-23T13:0{6 + index}:10Z",
                )
                for index, phase in enumerate(("1", "2", "3"))
            )
        )
    rows.append(
        ("SessionStatus", {"Status": "Finished"}, "2026-08-23T13:10:00Z")
    )
    return rows


def _normalize_transport(
    source: str, name: str, session_type: str
) -> tuple[RaceState, SessionEvidence, dict[str, RaceState]]:
    adapter = F1LiveAdapter("9001", source=source)
    state = RaceState()
    events = []
    snapshots: dict[str, RaceState] = {}
    for stream, payload, occurred_at in _provider_rows(name, session_type):
        emitted = adapter.ingest(
            {
                "stream": stream,
                "payload": payload,
                "source_timestamp": occurred_at,
            }
        )
        events.extend(emitted)
        for event in emitted:
            state = state.apply(event)
        if occurred_at.endswith("13:05:30Z"):
            snapshots["track_clear"] = state
        if occurred_at.endswith("13:06:00Z"):
            snapshots["restart"] = state
    if session_type == "Race":
        final_events = finalize_f1_classifications(
            adapter.streams["TimingData"],
            "2026-08-23T13:10:01Z",
            source=source,
        )
        events.extend(final_events)
        for event in final_events:
            state = state.apply(event)
    return state, SessionEvidence.from_events(tuple(events)), snapshots


@pytest.mark.parametrize(
    ("name", "session_type", "session_kind", "layout_family"),
    (
        ("Race", "Race", "race", "race"),
        ("Qualifying", "Qualifying", "qualifying", "qualifying"),
        ("Practice 1", "Practice", "practice_1", "practice"),
    ),
)
def test_live_and_static_transport_have_cross_session_product_parity(
    name: str,
    session_type: str,
    session_kind: str,
    layout_family: str,
) -> None:
    live = _normalize_transport("f1-signalr-public", name, session_type)
    static = _normalize_transport("f1-static-public", name, session_type)

    assert asdict(live[0]) == asdict(static[0])
    assert live[1] == static[1]
    assert live[0].session.session_kind == session_kind
    assert live[0].session.layout_family == layout_family
    assert len(live[1].laps_for_driver("44")) == 1
    assert len(live[1].pit_events_for_driver("44")) == 1
    assert live[1].pit_events_for_driver("44")[0].new_compound == "HARD"
    assert live[2]["track_clear"].session.status == "SUSPENDED"
    assert live[2]["track_clear"].session.display_status == "RED_FLAG"
    assert live[2]["restart"].session.status == "RUNNING"
    assert live[2]["restart"].session.display_status == "GREEN"
    assert live[0].drivers["44"].source_retired is False
    if session_type == "Qualifying":
        assert live[0].session.qualifying_phase == "Q3"
    if session_type == "Practice":
        assert live[0].drivers["44"].classification is None
    if session_type == "Race":
        assert live[0].drivers["44"].classification == "FINISHED"
