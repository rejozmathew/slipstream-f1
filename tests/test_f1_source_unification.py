from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError

import pytest

from slipstream.adapters.f1_historical import (
    STATIC_ROOT,
    F1HistoricalClient,
    F1HistoricalError,
    parse_json_stream,
    write_canonical_recording,
)
from slipstream.events import NormalizedEvent
from slipstream.evidence import SessionEvidence
from slipstream.f1_timing import (
    finalize_f1_classifications,
    merge_f1_provider_value,
    normalize_f1_timing,
)
from slipstream.historical_download import HistoricalSessionDownloader
from slipstream.library import ReplayLibrary, SessionDescriptor
from slipstream.lifecycle import is_retired_indicated, is_stopped, is_terminal
from slipstream.live import F1LiveAdapter, PublicLiveSession
from slipstream.playback import ReplayController
from slipstream.state import RaceState


def _apply(state: RaceState, events: list[NormalizedEvent]) -> RaceState:
    for event in events:
        state = state.apply(event)
    return state


def _timing(
    number: str,
    at: str,
    *,
    retired: bool,
    stopped: bool,
    laps: int | None,
) -> list[NormalizedEvent]:
    line = {
        "RacingNumber": number,
        "Retired": retired,
        "Stopped": stopped,
        **({"NumberOfLaps": laps} if laps is not None else {}),
    }
    return normalize_f1_timing(
        {"Lines": {number: line}},
        {"Lines": {number: line}},
        f"2026-08-23T{at}Z",
        source="f1-static-public",
    )


def test_json_stream_sparse_merge_preserves_explicit_false() -> None:
    rows = parse_json_stream(
        '01:10:09.491{"Lines":{"77":{"Retired":true,"Stopped":true}}}\n'
        '01:10:10.476{"Lines":{"77":{"Retired":false,"Stopped":false}}}'
    )
    merged = None
    for _offset, patch in rows:
        merged = merge_f1_provider_value(merged, patch)

    assert merged["Lines"]["77"] == {"Retired": False, "Stopped": False}


def test_live_and_historical_share_identical_timing_payloads() -> None:
    payload = {
        "Lines": {
            "77": {
                "RacingNumber": "77",
                "Position": "8",
                "NumberOfLaps": 2,
                "NumberOfPitStops": 1,
                "Retired": False,
                "Stopped": True,
                "Sectors": {"0": {"Value": "21.1"}},
            }
        }
    }
    emitted = []
    for source in ("f1-signalr-public", "f1-static-public"):
        adapter = F1LiveAdapter("11353", source=source)
        adapter.ingest(
            {
                "stream": "SessionInfo",
                "payload": {"Key": 11353},
                "source_timestamp": "2026-08-23T00:00:00Z",
            }
        )
        emitted.append(
            adapter.ingest(
                {
                    "stream": "TimingData",
                    "payload": payload,
                    "source_timestamp": "2026-08-23T01:10:09.491Z",
                }
            )[0]
        )

    assert emitted[0].payload == emitted[1].payload
    assert emitted[0].payload["source_condition"] == "STOPPED"


def test_official_timing_app_data_emits_three_cursor_safe_hamilton_stops() -> None:
    adapter = F1LiveAdapter("11353", source="f1-static-public")
    events: list[NormalizedEvent] = []

    def ingest(stream: str, payload: dict, at: str) -> None:
        events.extend(
            adapter.ingest(
                {
                    "stream": stream,
                    "payload": payload,
                    "source_timestamp": at,
                }
            )
        )

    ingest("SessionInfo", {"Key": 11353}, "2026-08-23T13:00:00Z")
    ingest(
        "TimingAppData",
        {
            "Lines": {
                "44": {
                    "RacingNumber": "44",
                    "Stints": {
                        "0": {
                            "Compound": "SOFT",
                            "New": "true",
                            "TotalLaps": 0,
                            "StartLaps": 0,
                        }
                    },
                }
            }
        },
        "2026-08-23T13:48:29.994Z",
    )
    ingest(
        "TimingData",
        {
            "Lines": {
                "44": {
                    "RacingNumber": "44",
                    "NumberOfLaps": 1,
                    "NumberOfPitStops": 0,
                    "InPit": False,
                }
            }
        },
        "2026-08-23T13:59:00Z",
    )

    observations = (
        (1, 2, "SOFT", "2026-08-23T14:00:25.507Z"),
        (2, 25, "HARD", "2026-08-23T15:00:16.710Z"),
        (3, 55, "SOFT", "2026-08-23T15:39:08.675Z"),
    )
    for ordinal, lap, new_compound, pit_at in observations:
        ingest(
            "TimingData",
            {
                "Lines": {
                    "44": {
                        "NumberOfLaps": lap - 1,
                        "NumberOfPitStops": ordinal,
                        "InPit": True,
                    }
                }
            },
            pit_at,
        )
        reveal_at = {
            1: "2026-08-23T14:26:45.248Z",
            2: "2026-08-23T15:00:47.107Z",
            3: "2026-08-23T15:39:42.431Z",
        }[ordinal]
        ingest(
            "TimingAppData",
            {
                "Lines": {
                    "44": {
                        "Stints": {
                            str(ordinal): {
                                "Compound": new_compound,
                                "New": "false" if ordinal == 1 else "true",
                                "TotalLaps": 3 if ordinal == 1 else 0,
                                "StartLaps": 3 if ordinal == 1 else 0,
                            }
                        }
                    }
                }
            },
            reveal_at,
        )
    evidence = SessionEvidence.from_events(tuple(events))
    pits = evidence.pit_events_for_driver("44")
    assert [(pit.ordinal, pit.lap) for pit in pits] == [(1, 2), (2, 25), (3, 55)]
    assert [(pit.previous_compound, pit.new_compound) for pit in pits] == [
        ("SOFT", "SOFT"),
        ("SOFT", "HARD"),
        ("HARD", "SOFT"),
    ]
    assert [pit.occurred_at for pit in pits] == [item[3] for item in observations]
    second_reveal = next(
        index
        for index, event in enumerate(events, start=1)
        if event.payload.get("pit_observation", {}).get("ordinal") == 2
    )
    assert evidence.pit_events_for_driver("44", event_limit=second_reveal - 1) == (
        pits[0],
    )
    assert evidence.pit_events_for_driver("44", event_limit=second_reveal) == (
        pits[0],
        pits[1],
    )


def test_official_completed_lap_quality_uses_stint_and_track_evidence() -> None:
    adapter = F1LiveAdapter("11353", source="f1-static-public")
    events: list[NormalizedEvent] = []

    def ingest(stream: str, payload: dict, at: str) -> None:
        events.extend(
            adapter.ingest(
                {
                    "stream": stream,
                    "payload": payload,
                    "source_timestamp": at,
                }
            )
        )

    ingest("SessionInfo", {"Key": 11353}, "2026-08-23T13:00:00Z")
    ingest("SessionStatus", {"Status": "Started"}, "2026-08-23T13:00:01Z")
    ingest("TrackStatus", {"Status": "1"}, "2026-08-23T13:00:02Z")
    ingest(
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
    )
    ingest(
        "TimingData",
        {
            "Lines": {
                "44": {
                    "NumberOfLaps": 1,
                    "LastLapTime": {"Value": "1:20.000"},
                }
            }
        },
        "2026-08-23T13:02:00Z",
    )
    ingest("TrackStatus", {"Status": "2"}, "2026-08-23T13:02:01Z")
    ingest(
        "TimingData",
        {
            "Lines": {
                "44": {
                    "NumberOfLaps": 2,
                    "LastLapTime": {"Value": "1:22.000"},
                }
            }
        },
        "2026-08-23T13:03:22Z",
    )

    laps = SessionEvidence.from_events(tuple(events)).laps_for_driver("44")
    assert laps[0].started_at == "2026-08-23T13:00:40Z"
    assert (laps[0].stint_number, laps[0].quality) == (1, "representative")
    assert laps[1].quality == "contaminated"
    assert laps[1].contamination_reasons == ("neutralized_track",)


def test_official_qualifying_parts_and_results_are_cursor_safe() -> None:
    adapter = F1LiveAdapter("11349", source="f1-static-public")
    events = list(
        adapter.ingest(
            {
                "stream": "SessionInfo",
                "payload": {"Key": 11349, "Name": "Qualifying", "Type": "Qualifying"},
                "source_timestamp": "2026-08-22T13:46:33Z",
            }
        )
    )
    events.extend(
        adapter.ingest(
            {
                "stream": "SessionData",
                "payload": {"Series": {"0": {"QualifyingPart": 1}}},
                "source_timestamp": "2026-08-22T13:46:45Z",
            }
        )
    )
    events.extend(
        adapter.ingest(
            {
                "stream": "TimingData",
                "payload": {
                    "Lines": {
                        "44": {
                            "RacingNumber": "44",
                            "BestLapTimes": {
                                "0": {"Value": "1:12.673", "Lap": 9},
                                "1": {},
                                "2": {},
                            },
                        }
                    }
                },
                "source_timestamp": "2026-08-22T14:18:00Z",
            }
        )
    )
    q1_state = _apply(RaceState(), events)
    assert q1_state.session.qualifying_phase == "Q1"
    assert q1_state.drivers["44"].qualifying_results == (72.673, None, None)
    assert q1_state.drivers["44"].qualifying_phase_reached == "Q1"

    q2_events = list(
        adapter.ingest(
            {
                "stream": "SessionData",
                "payload": {"Series": {"1": {"QualifyingPart": 2}}},
                "source_timestamp": "2026-08-22T14:23:59Z",
            }
        )
    )
    q2_events.extend(
        adapter.ingest(
            {
                "stream": "TimingData",
                "payload": {
                    "Lines": {
                        "44": {
                            "BestLapTimes": {"1": {"Value": "1:11.970", "Lap": 13}}
                        }
                    }
                },
                "source_timestamp": "2026-08-22T14:40:00Z",
            }
        )
    )
    q2_state = _apply(q1_state, q2_events)
    assert q2_state.session.qualifying_phase == "Q2"
    assert q2_state.drivers["44"].qualifying_results == (72.673, 71.97, None)
    assert q2_state.drivers["44"].qualifying_phase_reached == "Q2"


def test_official_minisectors_supply_timing_estimate_without_xy() -> None:
    sectors = [
        {"Segments": [{"Status": 0} for _ in range(8)]} for _ in range(3)
    ]
    merged = {"Lines": {"1": {"RacingNumber": "1", "Sectors": sectors}}}
    patch = {
        "Lines": {"1": {"Sectors": {"1": {"Segments": {"3": {"Status": 2049}}}}}}
    }
    events = normalize_f1_timing(
        merged,
        patch,
        "2026-08-23T13:04:00Z",
        source="f1-static-public",
    )

    assert events[0].payload["track_position"] == pytest.approx(12 / 24)
    assert "x" not in events[0].payload
    assert "y" not in events[0].payload

    reset_patch = {
        "Lines": {"1": {"Sectors": {"1": {"Segments": {"3": {"Status": 0}}}}}}
    }
    reset = normalize_f1_timing(
        merged,
        reset_patch,
        "2026-08-23T13:04:01Z",
        source="f1-static-public",
    )
    assert "track_position" not in reset[0].payload

    lap = normalize_f1_timing(
        merged,
        {"Lines": {"1": {"NumberOfLaps": 2}}},
        "2026-08-23T13:04:02Z",
        source="f1-static-public",
    )
    assert lap[0].payload["track_position"] == 0.0


def test_bot_transient_retired_and_stopped_retract_without_terminal_poison() -> None:
    state = RaceState()
    state = _apply(
        state,
        _timing("77", "01:10:09.491", retired=True, stopped=True, laps=2),
    )
    assert state.drivers["77"].source_condition == "RETIRED_INDICATED"
    assert is_retired_indicated(state.drivers["77"])
    assert not is_terminal(state.drivers["77"])

    state = _apply(
        state,
        _timing("77", "01:10:10.476", retired=False, stopped=False, laps=2),
    )
    bot = state.drivers["77"]
    assert bot.source_retired is False
    assert bot.source_stopped is False
    assert bot.source_condition == "RUNNING"
    assert bot.status == "RUNNING"
    assert not is_terminal(bot)


def test_stopped_resumes_on_explicit_source_false() -> None:
    state = _apply(
        RaceState(),
        _timing("31", "02:38:22.649", retired=False, stopped=True, laps=52),
    )
    assert is_stopped(state.drivers["31"])
    state = _apply(
        state,
        normalize_f1_timing(
            {
                "Lines": {
                    "31": {
                        "RacingNumber": "31",
                        "Retired": False,
                        "Stopped": False,
                        "NumberOfLaps": 52,
                    }
                }
            },
            {"Lines": {"31": {"Retired": False, "Stopped": False}}},
            "2026-08-23T02:38:23Z",
            source="f1-static-public",
        ),
    )
    assert state.drivers["31"].source_condition == "RUNNING"
    assert not is_stopped(state.drivers["31"])
    assert state.drivers["31"].track_position is None

    sectors = [{"Segments": [{"Status": 0} for _ in range(4)]} for _ in range(3)]
    state = _apply(
        state,
        normalize_f1_timing(
            {"Lines": {"31": {"Sectors": sectors}}},
            {"Lines": {"31": {"Sectors": {"0": {"Segments": {"0": {"Status": 2049}}}}}}},
            "2026-08-23T02:38:24Z",
            source="f1-static-public",
        ),
    )
    assert state.drivers["31"].track_position == pytest.approx(1 / 12)


def test_explicit_in_pit_false_recovers_to_running() -> None:
    state = RaceState().apply(
        normalize_f1_timing(
            {"Lines": {"1": {"InPit": True}}},
            {"Lines": {"1": {"InPit": True}}},
            "2026-08-23T01:00:00Z",
            source="f1-static-public",
        )[0]
    )
    state = state.apply(
        normalize_f1_timing(
            {"Lines": {"1": {"InPit": False}}},
            {"Lines": {"1": {"InPit": False}}},
            "2026-08-23T01:00:01Z",
            source="f1-static-public",
        )[0]
    )
    assert state.drivers["1"].source_condition == "RUNNING"


def test_explicit_finished_classification_outranks_stopped_flag() -> None:
    events = finalize_f1_classifications(
        {
            "Lines": {
                "1": {
                    "Position": "1",
                    "Stopped": True,
                    "Classification": "FINISHED",
                }
            }
        },
        "2026-08-23T03:10:00Z",
        source="f1-signalr-public",
    )
    assert events[0].payload["classification"] == "FINISHED"


@pytest.mark.parametrize(
    ("number", "at", "laps", "retired", "condition"),
    [
        ("3", "01:14:29.632", None, False, "STOPPED"),
        ("87", "01:34:12.592", 2, False, "STOPPED"),
        ("18", "02:30:02.568", 45, True, "RETIRED_INDICATED"),
        ("31", "02:38:22.649", 52, False, "STOPPED"),
        ("77", "02:53:07.662", 61, True, "RETIRED_INDICATED"),
        ("23", "02:58:57.577", 66, True, "RETIRED_INDICATED"),
    ],
)
def test_dutch_six_source_transitions_then_final_dnf(
    number: str, at: str, laps: int | None, retired: bool, condition: str
) -> None:
    state = _apply(
        RaceState(),
        _timing(number, at, retired=retired, stopped=True, laps=laps),
    )
    driver = state.drivers[number]
    assert driver.source_condition == condition
    assert driver.source_retired is retired
    assert driver.classification is None
    assert not is_terminal(driver)

    state = state.apply(
        NormalizedEvent(
            "timing",
            "2026-08-23T03:10:00Z",
            "f1-static-public",
            {"number": number, "classification": "DNF"},
        )
    )
    assert state.drivers[number].classification == "DNF"
    assert state.drivers[number].status == "DNF"
    assert is_terminal(state.drivers[number])


def test_live_adapter_uses_source_timestamp_for_cursor_semantics() -> None:
    adapter = F1LiveAdapter("11353")
    adapter.ingest(
        {
            "stream": "SessionInfo",
            "payload": {"Key": 11353, "StartDate": "2026-08-23T00:00:00Z"},
            "received_at": "2026-08-23T05:00:00Z",
            "source_timestamp": "2026-08-23T00:00:00Z",
        }
    )
    events = adapter.ingest(
        {
            "stream": "TimingData",
            "payload": {"Lines": {"3": {"Stopped": True, "Retired": False}}},
            "received_at": "2026-08-23T05:00:01Z",
            "source_timestamp": "2026-08-23T01:14:29.632Z",
        }
    )
    assert events[0].occurred_at == "2026-08-23T01:14:29.632Z"


def test_live_capture_finalizes_from_same_shared_f1_semantics_after_drain() -> None:
    rows = (
        {
            "stream": "SessionInfo",
            "payload": {"Key": 11353, "Name": "Race", "Type": "Race"},
            "source_timestamp": "2026-08-23T00:00:00Z",
        },
        {
            "stream": "TimingData",
            "payload": {"Lines": {"3": {"Stopped": True, "Retired": False}}},
            "source_timestamp": "2026-08-23T01:14:29.632Z",
        },
        {
            "stream": "SessionStatus",
            "payload": {"Status": "Finished"},
            "source_timestamp": "2026-08-23T03:10:00Z",
        },
    )
    live = PublicLiveSession(finalization_drain=0)
    asyncio.run(live.apply_rows("11353", rows))
    assert live.state.drivers["3"].classification == "DNF"


def test_live_finalization_waits_for_late_result_update() -> None:
    rows = (
        {
            "stream": "SessionInfo",
            "payload": {"Key": 11353, "Name": "Race", "Type": "Race"},
            "source_timestamp": "2026-08-23T00:00:00Z",
        },
        {
            "stream": "TimingData",
            "payload": {"Lines": {"3": {"Stopped": False, "Position": "20"}}},
            "source_timestamp": "2026-08-23T03:09:59Z",
        },
        {
            "stream": "SessionStatus",
            "payload": {"Status": "Finished"},
            "source_timestamp": "2026-08-23T03:10:00Z",
        },
        {
            "stream": "TimingData",
            "payload": {
                "Lines": {
                    "3": {
                        "Stopped": True,
                        "Classification": "DNF",
                    }
                }
            },
            "source_timestamp": "2026-08-23T03:10:01Z",
        },
    )
    live = PublicLiveSession(finalization_drain=0)
    asyncio.run(live.apply_rows("11353", rows))
    result_events = [
        event for event in live.events if event.payload.get("classification") == "DNF"
    ]
    assert [event.occurred_at for event in result_events] == [
        "2026-08-23T03:10:01Z"
    ]


def test_dutch_six_reconstruct_without_future_projection_and_finalize_together() -> None:
    adapter = F1LiveAdapter("11353", source="f1-static-public")
    state = RaceState()

    def ingest(stream: str, payload: dict, at: str) -> None:
        nonlocal state
        state = _apply(
            state,
            list(
                adapter.ingest(
                    {
                        "stream": stream,
                        "payload": payload,
                        "source_timestamp": f"2026-08-23T{at}Z",
                    }
                )
            ),
        )

    ingest("SessionInfo", {"Key": 11353}, "00:00:00")
    initial = {
        number: {"RacingNumber": number, "Retired": False, "Stopped": False}
        for number in ("3", "87", "18", "31", "77", "23")
    }
    ingest("TimingData", {"Lines": initial}, "00:00:01")
    assert all(
        driver.source_condition == "RUNNING" for driver in state.drivers.values()
    )

    ingest(
        "TimingData",
        {"Lines": {"77": {"Retired": True, "Stopped": True, "NumberOfLaps": 2}}},
        "01:10:09.491",
    )
    assert state.drivers["77"].source_condition == "RETIRED_INDICATED"
    ingest(
        "TimingData",
        {"Lines": {"77": {"Retired": False, "Stopped": False}}},
        "01:10:10.476",
    )
    assert state.drivers["77"].source_condition == "RUNNING"
    transitions = (
        ("3", "01:14:29.632", False, None, "STOPPED"),
        ("87", "01:34:12.592", False, 2, "STOPPED"),
        ("18", "02:30:02.568", True, 45, "RETIRED_INDICATED"),
        ("31", "02:38:22.649", False, 52, "STOPPED"),
        ("77", "02:53:07.662", True, 61, "RETIRED_INDICATED"),
        ("23", "02:58:57.577", True, 66, "RETIRED_INDICATED"),
    )
    for number, at, retired, laps, expected in transitions:
        assert state.drivers[number].source_condition == "RUNNING"
        line = {"Retired": retired, "Stopped": True}
        if laps is not None:
            line["NumberOfLaps"] = laps
        ingest("TimingData", {"Lines": {number: line}}, at)
        assert state.drivers[number].source_condition == expected
        assert state.drivers[number].classification is None

    ingest("SessionStatus", {"Status": "Finished"}, "03:10:00")
    state = _apply(
        state,
        finalize_f1_classifications(
            adapter.streams["TimingData"],
            "2026-08-23T03:10:00Z",
            source="f1-static-public",
        ),
    )
    assert {number: state.drivers[number].classification for number in state.drivers} == {
        "3": "DNF",
        "87": "DNF",
        "18": "DNF",
        "31": "DNF",
        "77": "DNF",
        "23": "DNF",
    }


def _descriptor() -> SessionDescriptor:
    return SessionDescriptor(
        key="11353",
        year=2026,
        meeting_key="1292",
        meeting_name="Dutch Grand Prix",
        session_name="Race",
        session_type="Race",
        circuit="Zandvoort",
        location="Zandvoort",
        date_start="2026-08-23T00:00:00Z",
        date_end="2026-08-23T03:10:00Z",
        gmt_offset="02:00:00",
        path=None,
        source="openf1",
        capabilities={},
    )


def _session_event(source: str) -> NormalizedEvent:
    return NormalizedEvent(
        "session",
        "2026-08-23T00:00:00Z",
        source,
        {
            "key": "11353",
            "name": "Race",
            "meeting_name": "Dutch Grand Prix",
            "session_type": "Race",
            "session_kind": "race",
            "layout_family": "race",
            "started_at": "2026-08-23T00:00:00Z",
            "ended_at": "2026-08-23T03:10:00Z",
            "lap": 1,
            "total_laps": 2,
            "status": "RUNNING",
        },
    )


def _timing_event(source: str) -> NormalizedEvent:
    return NormalizedEvent(
        "timing",
        "2026-08-23T00:01:00Z",
        source,
        {"number": "3", "lap": 1},
    )


def _valid_official_events() -> tuple[NormalizedEvent, ...]:
    events = [_session_event("f1-static-public")]
    for position in range(1, 11):
        events.append(
            NormalizedEvent(
                "timing",
                "2026-08-23T00:01:00Z",
                "f1-static-public",
                {
                    "number": str(position),
                    "position": position,
                    "lap": 1,
                    **({"track_position": 0.25} if position == 1 else {}),
                },
            )
        )
    events.append(
        NormalizedEvent(
            "session",
            "2026-08-23T00:02:00Z",
            "f1-static-public",
            {"lap": 2, "status": "FINISHED"},
        )
    )
    for position in range(1, 11):
        events.append(
            NormalizedEvent(
                "timing",
                "2026-08-23T00:02:00Z",
                "f1-static-public",
                {"number": str(position), "classification": "FINISHED"},
            )
        )
    return tuple(events)


def test_official_success_is_one_whole_source_and_never_calls_openf1(
    tmp_path: Path,
) -> None:
    class Official:
        def capture_events(self, key, *, year, session_identity):
            assert (str(key), year) == ("11353", 2026)
            assert session_identity["layout_family"] == "race"
            return _valid_official_events()

    class Fallback:
        def capture_session(self, _key):
            raise AssertionError("OpenF1 must not be called after official success")

    path = HistoricalSessionDownloader(
        official=Official(), fallback=Fallback()
    ).download(_descriptor(), tmp_path)

    assert path.name == "f1-static-11353.json"
    assert {item["source"] for item in json.loads(path.read_text())} == {
        "f1-static-public"
    }
    manifest = json.loads(
        (tmp_path / ".slipstream" / "sources" / "11353.json").read_text()
    )
    assert manifest["capabilities"]["positions"] is True
    assert manifest["capabilities"]["location_xy"] is False


def test_openf1_fallback_is_whole_session_without_official_event_mixing(
    tmp_path: Path,
) -> None:
    class Official:
        def capture_events(self, _key, *, year, session_identity):
            assert session_identity["session_kind"] == "race"
            raise RuntimeError(f"unsupported {year}")

    fallback_recording = json.loads(
        (
            Path(__file__).parent / "fixtures" / "openf1" / "session-9165.json"
        ).read_text()
    )

    class Fallback:
        def capture_session(self, _key):
            return fallback_recording

    path = HistoricalSessionDownloader(
        official=Official(), fallback=Fallback()
    ).download(_descriptor(), tmp_path)

    assert path.name == "openf1-11353.json"
    raw = json.loads(path.read_text())
    assert raw["source"] == "openf1"
    assert "f1-static-public" not in path.read_text()


def test_unusable_official_output_falls_back_as_one_whole_source(tmp_path: Path) -> None:
    class Official:
        def capture_events(self, _key, *, year, session_identity):
            assert year == 2026
            assert session_identity["meeting_name"] == "Dutch Grand Prix"
            return (_session_event("f1-static-public"),)

    fallback_recording = json.loads(
        (Path(__file__).parent / "fixtures" / "openf1" / "session-9165.json").read_text()
    )

    class Fallback:
        def capture_session(self, _key):
            return fallback_recording

    path = HistoricalSessionDownloader(
        official=Official(), fallback=Fallback()
    ).download(_descriptor(), tmp_path)
    assert path.name == "openf1-11353.json"


def test_replay_library_precedence_is_live_then_static_then_openf1(
    tmp_path: Path,
) -> None:
    catalog = {
        "format": "slipstream.openf1-catalog.v1",
        "schema_version": 1,
        "source": "openf1",
        "updated_at": "2026-08-23T00:00:00Z",
        "years": [2026],
        "meetings": {"1292": {"meeting_key": 1292, "meeting_name": "Dutch Grand Prix"}},
        "sessions": [
            {
                "session_key": 11353,
                "meeting_key": 1292,
                "session_name": "Race",
                "session_type": "Race",
                "date_start": "2026-08-23T00:00:00Z",
                "date_end": "2026-08-23T03:10:00Z",
                "year": 2026,
            }
        ],
    }
    (tmp_path / "catalog.json").write_text(json.dumps(catalog))
    for filename, source in (
        ("openf1.json", "openf1"),
        ("z-static.json", "f1-static-public"),
        ("a-live.json", "f1-signalr-public"),
    ):
        event = _session_event(source)
        (tmp_path / filename).write_text(
            json.dumps(
                [
                    {
                        "kind": event.kind,
                        "occurred_at": event.occurred_at,
                        "source": event.source,
                        "payload": event.payload,
                    }
                ]
            )
        )

    selected = ReplayLibrary(tmp_path).descriptors["11353"]
    assert selected.source == "f1-signalr-public"
    assert selected.path is not None and selected.path.name == "a-live.json"

    (tmp_path / "a-live.json").unlink()
    selected = ReplayLibrary(tmp_path).descriptors["11353"]
    assert selected.source == "f1-static-public"


def test_official_archive_uses_index_path_and_low_volume_streams() -> None:
    session_path = "2026/2026-08-23_Dutch_Grand_Prix/2026-08-23_Race"
    responses = {
        f"{STATIC_ROOT}/2026/Index.json": json.dumps(
            {"Meetings": [{"Sessions": [{"Key": 11353, "Path": session_path}]}]}
        ),
        f"{STATIC_ROOT}/{session_path}/SessionInfo.json": json.dumps(
            {
                "Key": 11353,
                "Name": "Race",
                "Type": "Race",
                "StartDate": "2026-08-23T15:00:00",
                "EndDate": "2026-08-23T17:00:00",
                "GmtOffset": "02:00:00",
            }
        ),
        f"{STATIC_ROOT}/{session_path}/DriverList.json": json.dumps(
            {"3": {"RacingNumber": "3", "Tla": "VER"}}
        ),
        f"{STATIC_ROOT}/{session_path}/TimingData.jsonStream": (
            '01:14:29.632{"Lines":{"3":{"RacingNumber":"3","Stopped":true,"Retired":false,"Position":"20"}}}'
        ),
        f"{STATIC_ROOT}/{session_path}/SessionStatus.jsonStream": (
            '00:56:45.791{"Status":"Started"}\n'
            '03:01:30.890{"Status":"Finished"}'
        ),
        f"{STATIC_ROOT}/{session_path}/ExtrapolatedClock.jsonStream": (
            '00:00:02.232{"Utc":"2026-08-23T12:06:45.008Z",'
            '"Remaining":"00:00:00","Extrapolating":false}\n'
            '00:56:46.230{"Utc":"2026-08-23T13:03:29.006Z",'
            '"Remaining":"01:59:59","Extrapolating":true}'
        ),
    }
    requests = []

    class Response:
        def __init__(self, body: str) -> None:
            self.body = body.encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return self.body

    def opener(request, timeout):
        assert timeout == 30
        requests.append(request)
        if request.full_url not in responses:
            raise HTTPError(request.full_url, 404, "missing", {}, None)
        return Response(responses[request.full_url])

    events = F1HistoricalClient(opener=opener).capture_events("11353", year=2026)
    driver_events = [event for event in events if event.payload.get("number") == "3"]

    assert any(
        event.occurred_at == "2026-08-23T13:21:12.408000Z"
        and event.payload.get("source_condition") == "STOPPED"
        for event in driver_events
    )
    assert driver_events[-1].payload["classification"] == "DNF"
    assert {event.source for event in events} == {"f1-static-public"}
    assert all(request.get_header("User-agent") == "BestHTTP" for request in requests)
    assert all(
        request.get_header("Accept-encoding") == "identity" for request in requests
    )


def test_official_full_session_info_seeds_sparse_stream_and_dynamic_full_is_final() -> None:
    session_path = "2026/Dutch/Race"
    responses = {
        f"{STATIC_ROOT}/2026/Index.json": json.dumps(
            {"Sessions": [{"Key": 11353, "Path": session_path}]}
        ),
        f"{STATIC_ROOT}/{session_path}/SessionInfo.json": json.dumps(
            {
                "Key": 11353,
                "Name": "Race",
                "Type": "Race",
                "StartDate": "2026-08-23T15:00:00",
                "EndDate": "2026-08-23T17:00:00",
                "GmtOffset": "02:00:00",
            }
        ),
        f"{STATIC_ROOT}/{session_path}/SessionInfo.jsonStream": (
            '00:00:10.000{"Name":"Race"}'
        ),
        f"{STATIC_ROOT}/{session_path}/TimingData.json": json.dumps(
            {
                "Lines": {
                    "3": {
                        "RacingNumber": "3",
                        "Position": "20",
                        "Stopped": True,
                        "Retired": False,
                    }
                }
            }
        ),
        f"{STATIC_ROOT}/{session_path}/SessionStatus.jsonStream": (
            '00:56:45.791{"Status":"Started"}\n'
            '03:01:30.890{"Status":"Finished"}'
        ),
        f"{STATIC_ROOT}/{session_path}/SessionData.jsonStream": (
            '00:56:45.791{"StatusSeries":{"4":'
            '{"Utc":"2026-08-23T13:03:28.567Z",'
            '"SessionStatus":"Started"}}}\n'
            '03:01:30.890{"StatusSeries":{"29":'
            '{"Utc":"2026-08-23T15:08:13.666Z",'
            '"SessionStatus":"Finished"}}}'
        ),
    }

    class Response:
        def __init__(self, body: str) -> None:
            self.body = body.encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return self.body

    def opener(request, timeout):
        assert timeout == 30
        if request.full_url not in responses:
            raise HTTPError(request.full_url, 404, "missing", {}, None)
        return Response(responses[request.full_url])

    events = F1HistoricalClient(opener=opener).capture_events("11353", year=2026)
    timing = [event for event in events if event.kind == "timing"]
    assert timing
    assert min(event.occurred_at for event in timing) == (
        "2026-08-23T15:08:13.666000Z"
    )
    assert timing[-1].payload["classification"] == "DNF"


def test_official_archive_fails_closed_without_absolute_clock_anchor() -> None:
    session_path = "2026/Dutch/Race"
    responses = {
        f"{STATIC_ROOT}/2026/Index.json": json.dumps(
            {"Sessions": [{"Key": 11353, "Path": session_path}]}
        ),
        f"{STATIC_ROOT}/{session_path}/SessionInfo.json": json.dumps(
            {
                "Key": 11353,
                "Name": "Race",
                "Type": "Race",
                "StartDate": "2026-08-23T15:00:00",
                "GmtOffset": "02:00:00",
            }
        ),
        f"{STATIC_ROOT}/{session_path}/TimingData.jsonStream": (
            '01:14:29.632{"Lines":{"3":{"Stopped":true}}}'
        ),
    }

    class Response:
        def __init__(self, body: str) -> None:
            self.body = body.encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return self.body

    def opener(request, timeout):
        if request.full_url not in responses:
            raise HTTPError(request.full_url, 404, "missing", {}, None)
        return Response(responses[request.full_url])

    with pytest.raises(F1HistoricalError, match="no reliable"):
        F1HistoricalClient(opener=opener).capture_events("11353", year=2026)


def test_s3_access_denied_is_absence_only_for_optional_official_topics() -> None:
    def forbidden(request, timeout):
        raise HTTPError(request.full_url, 403, "Access Denied", {}, None)

    client = F1HistoricalClient(opener=forbidden)
    assert client._get_optional_text("https://archive.test/LapCount.json") is None
    with pytest.raises(HTTPError) as error:
        client._get_json("https://archive.test/Index.json")
    assert error.value.code == 403


def test_sparse_session_info_never_overwrites_known_identity_with_placeholder() -> None:
    adapter = F1LiveAdapter("11353", source="f1-static-public")
    events = adapter.ingest(
        {
            "stream": "SessionInfo",
            "payload": {"Key": 11353},
            "source_timestamp": "2026-08-23T12:06:42.776Z",
        }
    )

    assert events[0].payload == {"key": "11353"}
    assert "name" not in events[0].payload
    assert "layout_family" not in events[0].payload


def test_authentic_dutch_11353_provider_rows_replay_end_to_end(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "f1_static" / "11353"
    session_path = "2026/2026-08-23_Dutch_Grand_Prix/2026-08-23_Race"
    responses = {
        f"{STATIC_ROOT}/2026/Index.json": json.dumps(
            {
                "Meetings": [
                    {
                        "Path": "2026-08-23_Dutch_Grand_Prix",
                        "Sessions": [{"Key": 11353, "Path": "2026-08-23_Race"}],
                    }
                ]
            }
        )
    }
    for path in fixture.iterdir():
        if path.suffix not in {".json", ".jsonStream"}:
            continue
        responses[f"{STATIC_ROOT}/{session_path}/{path.name}"] = path.read_text(
            encoding="utf-8-sig"
        )

    class Response:
        def __init__(self, body: str) -> None:
            self.body = body.encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return self.body

    def opener(request, timeout):
        assert timeout == 30
        if request.full_url not in responses:
            raise HTTPError(request.full_url, 404, "fixture topic absent", {}, None)
        return Response(responses[request.full_url])

    events = F1HistoricalClient(opener=opener).capture_events(
        "11353",
        year=2026,
        session_identity={
            "meeting_name": "Dutch Grand Prix",
            "session_name": "Race",
            "session_type": "Race",
            "session_kind": "race",
            "layout_family": "race",
            "circuit": "Zandvoort",
            "location": "Zandvoort",
            "date_start": "2026-08-23T13:00:00Z",
            "date_end": "2026-08-23T15:00:00Z",
            "gmt_offset": "02:00:00",
        },
    )
    recording = tmp_path / "f1-static-11353.json"
    write_canonical_recording(recording, events)
    (tmp_path / "catalog.json").write_text(
        json.dumps(
            {
                "format": "slipstream.openf1-catalog.v1",
                "schema_version": 1,
                "source": "openf1",
                "updated_at": "2026-08-24T00:00:00Z",
                "years": [2026],
                "meetings": {
                    "1292": {
                        "meeting_key": 1292,
                        "meeting_name": "Dutch Grand Prix",
                    }
                },
                "sessions": [
                    {
                        "session_key": 11353,
                        "meeting_key": 1292,
                        "session_name": "Race",
                        "session_type": "Race",
                        "date_start": "2026-08-23T13:00:00Z",
                        "date_end": "2026-08-23T15:00:00Z",
                        "gmt_offset": "02:00:00",
                        "year": 2026,
                        "location": "Zandvoort",
                        "circuit_short_name": "Zandvoort",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    library = ReplayLibrary(
        tmp_path, now=lambda: datetime(2026, 8, 24, tzinfo=UTC)
    )
    resource = library.get("11353")
    controller = ReplayController(resource.events)

    started = controller.seek("2026-08-23T13:03:28.567Z")
    assert started.session.meeting_name == "Dutch Grand Prix"
    assert started.session.name == "Race"
    assert started.session.session_kind == "race"
    assert started.session.layout_family == "race"
    assert started.session.started_at == "2026-08-23T13:00:00Z"
    assert started.session.local_time == "2026-08-23T15:03:28.567000+02:00"
    assert started.session.lap == 1
    assert started.session.total_laps == 72
    assert len(started.drivers) == 22

    lap_six = controller.seek("2026-08-23T13:41:01.645Z")
    assert lap_six.session.lap == 6
    assert lap_six.session.local_time == "2026-08-23T15:41:01.645000+02:00"

    transitions = (
        ("77", "2026-08-23T13:16:52.267Z", "RETIRED_INDICATED"),
        ("3", "2026-08-23T13:21:12.408Z", "STOPPED"),
        ("87", "2026-08-23T13:40:55.368Z", "STOPPED"),
        ("18", "2026-08-23T14:36:45.344Z", "RETIRED_INDICATED"),
        ("31", "2026-08-23T14:45:05.425Z", "STOPPED"),
        ("77", "2026-08-23T14:59:50.438Z", "RETIRED_INDICATED"),
        ("23", "2026-08-23T15:05:40.353Z", "RETIRED_INDICATED"),
    )
    for number, occurred_at, condition in transitions:
        state = controller.seek(occurred_at)
        assert state.drivers[number].source_condition == condition
        assert state.drivers[number].classification is None

    recovered = controller.seek("2026-08-23T13:16:53.252Z")
    assert recovered.drivers["77"].source_condition == "RUNNING"
    assert recovered.drivers["77"].source_retired is False
    assert recovered.drivers["77"].source_stopped is False
    assert all(driver.classification is None for driver in recovered.drivers.values())

    final = controller.seek("2026-08-23T15:28:47.876Z")
    classifications = [driver.classification for driver in final.drivers.values()]
    assert classifications.count("FINISHED") == 16
    assert classifications.count("DNF") == 6
    assert final.session.status == "FINISHED"
    assert final.session.lap == final.session.total_laps == 72
    assert resource.descriptor.position_mode == "timing_estimate"
    assert any(driver.track_position is not None for driver in final.drivers.values())
    assert all(driver.x is None and driver.y is None for driver in final.drivers.values())
    assert controller.events[-1].occurred_at == "2026-08-23T15:28:47.876000Z"


def test_official_index_composes_year_meeting_and_relative_session_paths() -> None:
    index_url = f"{STATIC_ROOT}/2026/Index.json"
    payload = {
        "Meetings": [
            {
                "Path": "2026-08-23_Dutch_Grand_Prix",
                "Sessions": [{"Key": 11353, "Path": "2026-08-23_Race"}],
            }
        ]
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(payload).encode()

    def opener(request, timeout):
        assert request.full_url == index_url
        assert timeout == 30
        return Response()

    resolved = F1HistoricalClient(opener=opener).resolve_session(2026, "11353")
    assert resolved.path == (
        "2026/2026-08-23_Dutch_Grand_Prix/2026-08-23_Race"
    )
