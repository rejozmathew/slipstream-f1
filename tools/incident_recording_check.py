"""Explicit original-recording check; evidence is deliberately not committed.

Run with SLIPSTREAM_INCIDENT_DIR pointing to the preserved handoff recordings:
python -m pytest tools/incident_recording_check.py -q
"""

import hashlib
import os
from pathlib import Path

from slipstream.playback import ReplayController
from slipstream.replay import load_events, replay

INCIDENT_SHA256 = "5bc62d73f6c0542b30bbc416c6d3f95ba26faed27915d5b2ebe70c476077d61c"


def _resolve_evidence_path():
    root = os.environ.get("SLIPSTREAM_INCIDENT_DIR")
    assert root, (
        "Set SLIPSTREAM_INCIDENT_DIR to the preserved original handoff recordings"
    )
    path = Path(root) / "live-11357.json"
    assert path.is_file(), f"Evidence missing: {path}"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == INCIDENT_SHA256
    return path


def test_qualifying_incident_evidence_invariants_and_playback_isolation():
    """Verify live-11357.json evidence counts, timing boundaries, and independent playback cursors."""
    path = _resolve_evidence_path()
    events = load_events(path)
    assert len(events) == 190, f"Expected 190 events, found {len(events)}"

    timing_events = [e for e in events if e.kind == "timing"]
    driver_events = [e for e in events if e.kind == "driver"]
    assert len(timing_events) == 101, (
        f"Expected 101 timing events, got {len(timing_events)}"
    )
    assert len(driver_events) == 44, (
        f"Expected 44 driver events, got {len(driver_events)}"
    )

    # Requirement: At 14:05:08 UTC no drivers; at 14:13:20 UTC 22 drivers with best_lap fields.
    state_early = replay(events, at="2026-09-05T14:05:08Z")
    assert len(state_early.drivers) == 0

    state_q1 = replay(events, at="2026-09-05T14:13:20Z")
    assert len(state_q1.drivers) == 22
    drivers_with_best_lap = [
        d for d in state_q1.drivers.values() if d.best_lap is not None
    ]
    assert len(drivers_with_best_lap) == 22, (
        f"Expected 22 drivers with best_lap at 14:13:20 UTC, found {len(drivers_with_best_lap)}"
    )

    # Independent viewer cursors: controllers over the same event stream operate independently
    ctrl_a = ReplayController(events)
    ctrl_b = ReplayController(events)

    ctrl_a.seek("2026-09-05T14:05:08Z")
    assert ctrl_a.cursor < len(ctrl_a.events)
    assert len(ctrl_a.state.drivers) == 0

    ctrl_b.seek("2026-09-05T14:13:20Z")
    assert len(ctrl_b.state.drivers) == 22
    # Ensure ctrl_a was not mutated by ctrl_b's seek operations
    assert len(ctrl_a.state.drivers) == 0
