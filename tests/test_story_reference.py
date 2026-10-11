from test_story import at, event, story


def qualifying():
    return [
        event("session", 0, key="q", layout_family="qualifying", session_kind="qualifying", qualifying_phase="Q3", status="RUNNING"),
        event("driver", 1, number="4", code="NOR", position=1, best_lap="1:20.000"),
        event("driver", 1, number="16", code="LEC", position=2, best_lap="1:20.500"),
    ]


def test_flag_alone_does_not_publish_pole_and_explicit_completion_is_cursor_gated():
    events = qualifying() + [event("session", 10, status="FINISHED")]
    assert not any(e["kind"] == "POLE" for e in story(events)["events"])
    events += [event("session", 20, session_complete=True)]
    assert not any(e["kind"] == "POLE" for e in story(events, len(events) - 1)["events"])
    pole = next(e for e in story(events)["events"] if e["kind"] == "POLE")
    assert pole["driverNumbers"] == ["4", "16"]
    assert pole["state"] == "provisional"
    assert pole["data"]["settled"] is True
    assert pole["data"]["lapTime"] == 80
    events += [event("session", 21, session_complete=True)]
    assert sum(e["kind"] == "POLE" for e in story(events)["events"]) == 1


def test_elimination_requires_explicit_source_fact_not_position_or_flag():
    events = qualifying() + [event("timing", 5, number="16", position=20), event("session", 10, status="FINISHED")]
    assert not any(e["kind"] == "ELIMINATED" for e in story(events)["events"])
    events += [event("timing", 11, number="16", qualifying_eliminated=True, qualifying_phase_reached="Q1")]
    eliminated = next(e for e in story(events)["events"] if e["kind"] == "ELIMINATED")
    assert eliminated["driverNumbers"] == ["16"]
    assert eliminated["data"]["phase"] == "Q1"


def test_new_q3_lap_can_publish_provisional_pole_but_result_packet_cannot():
    events = qualifying() + [event("timing", 5, number="4", best_lap="1:19.000")]
    assert not any(e["kind"] == "PROVISIONAL_POLE" for e in story(events)["events"])
    events += [event("timing", 8, number="4", best_lap="1:18.000", lap_observation={"lap": 4, "started_at": at(0), "duration": 78, "lap_validity": "VALID"})]
    pole = next(e for e in story(events)["events"] if e["kind"] == "PROVISIONAL_POLE")
    assert pole["state"] == "provisional"
    assert pole["data"]["lapTime"] == 78
