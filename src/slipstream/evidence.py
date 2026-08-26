"""Deterministic source-neutral session evidence outside RaceState snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from .events import NormalizedEvent, parse_timestamp
from .lifecycle import active_participants as _active_participants
from .state import RaceState


@dataclass(frozen=True)
class LapObservation:
    """One factual completed-lap observation; analytics are derived elsewhere."""

    lap: int
    started_at: str
    duration: float | None = None
    sector_1: float | None = None
    sector_2: float | None = None
    sector_3: float | None = None
    compound: str | None = None
    stint_number: int | None = None
    tyre_age: int | None = None
    qualifying_phase: str = "UNKNOWN"
    tyre_usage: str = "UNKNOWN"
    lap_validity: str = "UNKNOWN"
    pit_in: bool | None = None
    pit_out: bool | None = None
    pit_occurred_at: str | None = None
    previous_compound: str | None = None
    new_compound: str | None = None
    stop_duration: float | None = None
    pit_lane_duration: float | None = None
    quality: str = "unknown"
    contamination_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class LapEvidence:
    sequence: int
    occurred_at: str
    driver_number: str
    observation: LapObservation


@dataclass(frozen=True)
class CompletedGapEvidence:
    """One car-to-car gap sampled only when the behind car completed a lap."""

    sequence: int
    occurred_at: str
    lap: int
    ahead_driver_number: str
    behind_driver_number: str
    gap_seconds: float


@dataclass(frozen=True)
class PitEvent:
    """One viewer-oriented pit event backed only by observed source fields."""

    sequence: int
    occurred_at: str
    driver_number: str
    lap: int
    previous_compound: str | None = None
    new_compound: str | None = None
    stop_duration: float | None = None
    pit_lane_duration: float | None = None


@dataclass(frozen=True)
class SessionEvidence:
    """Queryable evidence reconstructed deterministically from normalized events."""

    lap_observations: tuple[LapEvidence, ...] = ()
    completed_gaps: tuple[CompletedGapEvidence, ...] = ()

    @classmethod
    def from_events(
        cls,
        events: tuple[NormalizedEvent, ...],
        *,
        cutoff: str | None = None,
    ) -> SessionEvidence:
        """Build evidence from normalized events.

        v2.1 Scenario 20: when ``cutoff`` is provided (the session's evidence
        cutoff / date_start), any observation whose ``started_at`` is *after*
        the cutoff is a cross-meeting / future-evidence integrity violation and
        is rejected **loudly** (``ValueError``) rather than silently degraded
        to an ordinary ``UNKNOWN``. The deterministic replay path (``at`` /
        ``event_limit``) still filters by cursor and is unaffected.
        """
        cutoff_dt = parse_timestamp(cutoff) if cutoff is not None else None
        observations: list[LapEvidence] = []
        completed_gaps: list[CompletedGapEvidence] = []
        state = RaceState()
        for sequence, event in enumerate(events, start=1):
            state = state.apply(event)
            payload = event.payload.get("lap_observation")
            driver_number = event.payload.get("number")
            if event.kind != "timing" or not isinstance(payload, dict):
                continue
            if driver_number is None:
                continue
            values = dict(payload)
            values["contamination_reasons"] = tuple(
                values.get("contamination_reasons", ())
            )
            observation = LapObservation(**values)
            if (
                cutoff_dt is not None
                and observation.started_at
                and parse_timestamp(observation.started_at) > cutoff_dt
            ):
                raise ValueError(
                    "future-evidence integrity violation: observation "
                    f"lap={observation.lap} started_at={observation.started_at} "
                    f"is after the session evidence cutoff {cutoff!r}; "
                    "rejected loudly (v2.1 Scenario 20) rather than degraded "
                    "to UNKNOWN"
                )
            observations.append(
                LapEvidence(
                    sequence=sequence,
                    occurred_at=event.occurred_at,
                    driver_number=str(driver_number),
                    observation=observation,
                )
            )
            behind = state.drivers.get(str(driver_number))
            if behind is None or behind.position is None:
                continue
            ahead = next(
                (
                    driver
                    for driver in state.drivers.values()
                    if driver.position == behind.position - 1
                ),
                None,
            )
            gap = _numeric_interval(behind.interval_to_ahead)
            if ahead is not None and gap is not None:
                completed_gaps.append(
                    CompletedGapEvidence(
                        sequence=sequence,
                        occurred_at=event.occurred_at,
                        lap=observation.lap,
                        ahead_driver_number=ahead.number,
                        behind_driver_number=behind.number,
                        gap_seconds=gap,
                    )
                )
        return cls(tuple(observations), tuple(completed_gaps))

    def append(
        self,
        event: NormalizedEvent,
        *,
        sequence: int,
        state: RaceState,
        cutoff: str | None = None,
    ) -> SessionEvidence:
        """Append evidence for one event using its canonical post-event state."""

        payload = event.payload.get("lap_observation")
        driver_number = event.payload.get("number")
        if (
            event.kind != "timing"
            or not isinstance(payload, dict)
            or driver_number is None
        ):
            return self
        values = dict(payload)
        values["contamination_reasons"] = tuple(values.get("contamination_reasons", ()))
        observation = LapObservation(**values)
        if (
            cutoff is not None
            and observation.started_at
            and parse_timestamp(observation.started_at) > parse_timestamp(cutoff)
        ):
            raise ValueError(
                "future-evidence integrity violation: observation "
                f"lap={observation.lap} started_at={observation.started_at} "
                f"is after the session evidence cutoff {cutoff!r}; "
                "rejected loudly (v2.1 Scenario 20) rather than degraded "
                "to UNKNOWN"
            )
        lap = LapEvidence(
            sequence=sequence,
            occurred_at=event.occurred_at,
            driver_number=str(driver_number),
            observation=observation,
        )
        gaps = self.completed_gaps
        behind = state.drivers.get(str(driver_number))
        if behind is not None and behind.position is not None:
            ahead = next(
                (
                    driver
                    for driver in state.drivers.values()
                    if driver.position == behind.position - 1
                ),
                None,
            )
            gap = _numeric_interval(behind.interval_to_ahead)
            if ahead is not None and gap is not None:
                gaps += (
                    CompletedGapEvidence(
                        sequence=sequence,
                        occurred_at=event.occurred_at,
                        lap=observation.lap,
                        ahead_driver_number=ahead.number,
                        behind_driver_number=behind.number,
                        gap_seconds=gap,
                    ),
                )
        return SessionEvidence(self.lap_observations + (lap,), gaps)

    def laps_for_driver(
        self,
        driver_number: str,
        *,
        at: str | None = None,
        event_limit: int | None = None,
    ) -> tuple[LapObservation, ...]:
        """Return evidence available at a deterministic replay time or cursor."""

        if at is not None and event_limit is not None:
            raise ValueError("evidence accepts either at or event_limit, not both")
        cutoff = parse_timestamp(at) if at is not None else None
        return tuple(
            item.observation
            for item in self.lap_observations
            if item.driver_number == str(driver_number)
            and (event_limit is None or item.sequence <= event_limit)
            and (cutoff is None or parse_timestamp(item.occurred_at) <= cutoff)
        )

    def pit_events_for_driver(
        self,
        driver_number: str,
        *,
        at: str | None = None,
        event_limit: int | None = None,
    ) -> tuple[PitEvent, ...]:
        if at is not None and event_limit is not None:
            raise ValueError("evidence accepts either at or event_limit, not both")
        cutoff = parse_timestamp(at) if at is not None else None
        return tuple(
            PitEvent(
                sequence=item.sequence,
                occurred_at=(item.observation.pit_occurred_at or item.occurred_at),
                driver_number=item.driver_number,
                lap=item.observation.lap,
                previous_compound=item.observation.previous_compound,
                new_compound=item.observation.new_compound,
                stop_duration=item.observation.stop_duration,
                pit_lane_duration=item.observation.pit_lane_duration,
            )
            for item in self.lap_observations
            if item.driver_number == str(driver_number)
            and item.observation.pit_occurred_at is not None
            and (event_limit is None or item.sequence <= event_limit)
            and (cutoff is None or parse_timestamp(item.occurred_at) <= cutoff)
        )

    def completed_gap_history(
        self,
        ahead_driver_number: str,
        behind_driver_number: str,
        *,
        event_limit: int | None = None,
    ) -> tuple[CompletedGapEvidence, ...]:
        """Return completed-lap gap samples for one factual ordered pair."""

        return tuple(
            item
            for item in self.completed_gaps
            if item.ahead_driver_number == str(ahead_driver_number)
            and item.behind_driver_number == str(behind_driver_number)
            and (event_limit is None or item.sequence <= event_limit)
        )

    # ------------------------------------------------------------------
    # v2.1 Phase B: strategy evidence primitives (consumed by Phase C)
    # ------------------------------------------------------------------

    def dry_compound_history(
        self,
        driver_number: str,
        *,
        at: str | None = None,
        event_limit: int | None = None,
    ) -> tuple[str, ...]:
        """Return the distinct dry compounds a driver has used, first-seen order.

        v2.1 §15: the per-driver dry-tyre requirement state is computed from
        this history + the rule profile. Wet/intermediate compounds are
        excluded — only the *dry* specification set counts toward the
        two-dry-obligation (FIA 2026 B6.3.6).
        """
        if at is not None and event_limit is not None:
            raise ValueError("evidence accepts either at or event_limit, not both")
        cutoff = parse_timestamp(at) if at is not None else None
        seen: dict[str, None] = {}
        for item in self.lap_observations:
            if item.driver_number != str(driver_number):
                continue
            if event_limit is not None and item.sequence > event_limit:
                continue
            if cutoff is not None and parse_timestamp(item.occurred_at) > cutoff:
                continue
            compound = item.observation.compound
            if compound is None:
                continue
            upper = compound.upper()
            if upper in {"WET", "INTERMEDIATE"}:
                continue
            seen.setdefault(upper, None)
        return tuple(seen)

    def pit_lane_durations(
        self,
        *,
        at: str | None = None,
        event_limit: int | None = None,
    ) -> tuple[float, ...]:
        """Return all observed pit-lane durations (for pit-loss baseline).

        v2.1 §17.1: raw pit-lane duration is *not* a defensible Net Pit Loss,
        but it is the only observed input available before Phase C derives
        the full metric.
        """
        if at is not None and event_limit is not None:
            raise ValueError("evidence accepts either at or event_limit, not both")
        cutoff = parse_timestamp(at) if at is not None else None
        return tuple(
            item.observation.pit_lane_duration
            for item in self.lap_observations
            if item.observation.pit_lane_duration is not None
            and (event_limit is None or item.sequence <= event_limit)
            and (cutoff is None or parse_timestamp(item.occurred_at) <= cutoff)
        )

    def stint_lengths(
        self,
        driver_number: str,
        *,
        at: str | None = None,
        event_limit: int | None = None,
    ) -> tuple[int, ...]:
        """Return per-stint lap counts for a driver, in stint order.

        v2.1 §12: stint life is a first-class strategy input. A stint is
        delimited by a pit-in event; the final (in-progress) stint is
        included with the laps accumulated so far.
        """
        if at is not None and event_limit is not None:
            raise ValueError("evidence accepts either at or event_limit, not both")
        cutoff = parse_timestamp(at) if at is not None else None
        stints: list[int] = []
        current = 0
        for item in self.lap_observations:
            if item.driver_number != str(driver_number):
                continue
            if event_limit is not None and item.sequence > event_limit:
                continue
            if cutoff is not None and parse_timestamp(item.occurred_at) > cutoff:
                continue
            if item.observation.pit_in is True:
                if current > 0:
                    stints.append(current)
                current = 0
            else:
                current += 1
        if current > 0:
            stints.append(current)
        return tuple(stints)


# ----------------------------------------------------------------------
# v2.1 Phase B: active-runner filter (v2.1 §18)
# ----------------------------------------------------------------------


def active_runners(state: RaceState) -> tuple[str, ...]:
    """Return driver numbers of *active runners* at the current cursor.

    v2.1 §18: field distributions (starting tyre, stop count, sequences)
    are over active runners only. Retired / DNS / excluded drivers are
    excluded. The predicate is derived from the driver's current status,
    never hard-coded to a fixed grid size.

    Delegates to the canonical ``lifecycle.active_participants`` concept so
    there is a single status vocabulary across the codebase (v2.1 §8).
    """
    return _active_participants(state)


def _numeric_interval(value: str | None) -> float | None:
    if not value or "lap" in value.casefold():
        return None
    try:
        return float(value.lstrip("+"))
    except ValueError:
        return None
