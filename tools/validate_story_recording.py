"""Read-only full/prefix truth audit against a private normalized recording.

No recording data is written or bundled. Times default to the design review's
regression offsets from the first RUNNING event at/after scheduled start.
"""

from __future__ import annotations

import argparse
import json
from bisect import bisect_right
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from time import perf_counter

from slipstream.analytics import build_analytics_snapshot
from slipstream.events import parse_timestamp
from slipstream.evidence import SessionEvidence
from slipstream.library import ReplayLibrary, ReplayResource
from slipstream.weekend import ContextAvailability


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--offsets", default="0,743,1179,1184,2400,3450,4766,4830,6150")
    parser.add_argument("--start", help="Explicit UTC origin instead of observed session start")
    args = parser.parse_args()
    started = perf_counter()
    resource = ReplayLibrary(args.recording).get()
    resource.prepare()
    scheduled = parse_timestamp(resource.descriptor.date_start)
    origin = parse_timestamp(args.start) if args.start else next((
        parse_timestamp(event.occurred_at) for event in resource.events
        if event.kind == "session" and event.payload.get("status") == "RUNNING"
        and parse_timestamp(event.occurred_at) >= scheduled
    ), scheduled)
    controller = resource.controller()
    rows = []
    for seconds in [float(item) for item in args.offsets.split(",")]:
        at = (origin + timedelta(seconds=seconds)).isoformat()
        seq = bisect_right(resource.timestamps, parse_timestamp(at))
        events = resource.events[:seq]
        state, evidence = SessionEvidence.reduce_events(events)
        assert asdict(controller.seek_cursor(seq)) == asdict(state), f"state mismatch at {seconds}"
        full_story = resource.evidence.story.snapshot(seq, at, limit=None)
        assert full_story == evidence.story.snapshot(seq, at, limit=None), f"story mismatch at {seconds}"
        truncated = ReplayResource(resource.descriptor, events, final_state=state,
            evidence=evidence, replay_available=resource.replay_available,
            recording_version=resource.recording_version)
        options = {"sequence": seq, "as_of": at, "context": ContextAvailability("unavailable")}
        full_analytics = build_analytics_snapshot(resource, state, **options)
        cut_analytics = build_analytics_snapshot(truncated, state, **options)
        assert full_analytics == cut_analytics, f"analytics mismatch at {seconds}"
        rows.append({"offsetSeconds": seconds, "at": at, "sequence": seq,
                     "stories": full_story["total"], "state": "equal", "story": "equal", "analytics": "equal"})
        print(json.dumps(rows[-1]), flush=True)
    print(json.dumps({"sessionKey": resource.descriptor.key, "events": len(resource.events),
                      "origin": origin.isoformat(), "cutoffs": len(rows),
                      "elapsedSeconds": round(perf_counter() - started, 3), "status": "PASS"}))


if __name__ == "__main__":
    main()
