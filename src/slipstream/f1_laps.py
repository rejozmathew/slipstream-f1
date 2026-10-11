"""Associate sparse official lap facts without synthesizing lap numbers."""

from dataclasses import replace

from .events import NormalizedEvent, parse_timestamp


class F1LapReconciler:
    """A time and a changed counter must belong to the same finish update.

    Five source-clock seconds admit split packets, not a later pit exit or
    another lap. Unmatched updates still update current timing, but cannot
    author a completed-lap observation with a guessed number.
    """

    def __init__(
        self, events: tuple[NormalizedEvent, ...] | list[NormalizedEvent] = ()
    ):
        self.seen = set()
        self.counts = {}
        self.pending_counts = {}
        self.pending_times = {}
        self.phases = {}
        for event in events:
            observation = event.payload.get("lap_observation")
            if event.kind == "timing" and isinstance(observation, dict):
                self.seen.add(
                    (
                        str(event.payload["number"]),
                        observation.get("qualifying_phase", "UNKNOWN"),
                        observation["lap"],
                    )
                )

    def reconcile(self, events, patch, phase, *, initial=False, lap_annotations=None):
        lines = patch.get("Lines", {}) if isinstance(patch, dict) else {}
        result = []
        for event in events:
            payload = dict(event.payload)
            number = str(payload["number"])
            line = lines.get(number, {})
            observation = payload.pop("lap_observation", None)
            if observation is not None and (
                observation.get("duration") is None or observation["duration"] <= 0
            ):
                observation = None
            now = parse_timestamp(event.occurred_at)
            time_patch = line.get("LastLapTime", {})
            cleared_time = (
                isinstance(time_patch, dict) and time_patch.get("Value") == ""
            )
            if (
                self.phases.get(number) != phase
                or initial
                or "InPit" in line
                or "NumberOfPitStops" in line
                or cleared_time
            ):
                self.pending_counts.pop(number, None)
                self.pending_times.pop(number, None)
            self.phases[number] = phase
            for pending in (self.pending_counts, self.pending_times):
                if (
                    number in pending
                    and not 0 <= (now - pending[number][1]).total_seconds() <= 5
                ):
                    pending.pop(number)
            count = payload.get("lap")
            if "NumberOfLaps" in line and isinstance(count, int):
                if count != self.counts.get(number):
                    self.pending_counts[number] = (count, now)
                self.counts[number] = count
            # A subscription snapshot repeats the last known lap. It is
            # not a fresh time waiting to be assigned to a later counter.
            if observation is not None and (
                not initial or (number, phase, count) not in self.seen
            ):
                self.pending_times[number] = (observation, now)
            counter = self.pending_counts.get(number)
            timed = self.pending_times.get(number)
            if counter and timed:
                key = (number, phase, counter[0])
                if key not in self.seen and counter[0] > 0:
                    matched = {**timed[0], "lap": counter[0]}
                    annotation = (
                        (lap_annotations or {}).get(number, {}).get(counter[0], {})
                    )
                    reasons = [
                        reason
                        for reason in matched["contamination_reasons"]
                        if reason not in {"pit_in", "pit_out"}
                    ]
                    for field in ("pit_in", "pit_out"):
                        matched[field] = annotation.get(field)
                        if annotation.get(field) is True:
                            reasons.append(field)
                    matched["contamination_reasons"] = reasons
                    matched["quality"] = (
                        "unknown"
                        if "neutralization_end_unknown" in reasons
                        else "contaminated"
                        if reasons
                        else "representative"
                    )
                    payload["lap_observation"] = matched
                    self.seen.add(key)
                    self.pending_counts.pop(number, None)
                    self.pending_times.pop(number, None)
            result.append(replace(event, payload=payload))
        return result
