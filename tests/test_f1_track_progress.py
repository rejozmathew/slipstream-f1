"""Mini-sector recolouring must never masquerade as a new car position."""

import pytest

from slipstream.live import F1LiveAdapter


@pytest.mark.parametrize("source", ["f1-signalr-public", "f1-static-public"])
def test_position_ignores_recolours_and_repeated_counts_but_recovers_after_reset(
    source,
):
    adapter = F1LiveAdapter("11384", source=source)
    adapter.ingest(
        {
            "stream": "SessionInfo",
            "payload": {"Key": 11384},
            "source_timestamp": "2026-10-10T13:30:00Z",
        }
    )
    seconds = 0

    def timing(line):
        nonlocal seconds
        seconds += 1
        return adapter.ingest(
            {
                "stream": "TimingData",
                "payload": {"Lines": {"27": line}},
                "source_timestamp": f"2026-10-10T13:30:{seconds:02d}Z",
            }
        )[0].payload

    def segment(index, status):
        return {"Sectors": {"0": {"Segments": {str(index): {"Status": status}}}}}

    sectors = [{"Segments": [{"Status": 0} for _ in range(8)]} for _ in range(3)]
    timing({"NumberOfLaps": 1, "InPit": False, "Sectors": sectors})
    assert timing(segment(5, 2051))["track_position"] == pytest.approx(6 / 24)
    assert timing(segment(6, 2051))["track_position"] == pytest.approx(7 / 24)
    # Real Singapore feed pattern: an earlier purple mini-sector becomes green
    # after another driver improves it. The car has not gone backwards.
    assert "track_position" not in timing(segment(5, 2049))
    assert "track_position" not in timing(segment(6, 2051))
    assert "track_position" not in timing({"NumberOfLaps": 1})
    assert timing(segment(7, 2048))["track_position"] == pytest.approx(8 / 24)
    assert timing({"NumberOfLaps": 2})["track_position"] == 0
    assert "track_position" not in timing({"Sectors": sectors})
    assert timing(segment(0, 2049))["track_position"] == pytest.approx(1 / 24)
    assert timing(segment(5, 2049))["track_position"] == pytest.approx(6 / 24)


def test_recolour_and_new_progress_in_same_patch_use_only_new_progress():
    adapter = F1LiveAdapter("11384")
    adapter.ingest(
        {
            "stream": "SessionInfo",
            "payload": {"Key": 11384},
            "source_timestamp": "2026-10-10T13:30:00Z",
        }
    )
    sectors = [{"Segments": [{"Status": 0} for _ in range(8)]} for _ in range(3)]
    # A still-purple marker from the previous lap must not win over a newly
    # completed mini-sector in this lap merely because its index is larger.
    sectors[2]["Segments"][6]["Status"] = 2051
    adapter.ingest(
        {
            "stream": "TimingData",
            "payload": {"Lines": {"16": {"Sectors": sectors}}},
            "source_timestamp": "2026-10-10T13:30:01Z",
        }
    )
    events = adapter.ingest(
        {
            "stream": "TimingData",
            "payload": {
                "Lines": {
                    "16": {
                        "Sectors": {
                            "0": {"Segments": {"2": {"Status": 2049}}},
                            "2": {"Segments": {"6": {"Status": 2049}}},
                        }
                    }
                }
            },
            "source_timestamp": "2026-10-10T13:30:02Z",
        }
    )
    assert events[0].payload["track_position"] == pytest.approx(3 / 24)
