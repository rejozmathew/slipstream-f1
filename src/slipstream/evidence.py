"""Deterministic source-neutral session evidence outside RaceState snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from .events import NormalizedEvent, parse_timestamp


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

    @classmethod
    def from_events(cls, events: tuple[NormalizedEvent, ...]) -> SessionEvidence:
        observations: list[LapEvidence] = []
        for sequence, event in enumerate(events, start=1):
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
            observations.append(
                LapEvidence(
                    sequence=sequence,
                    occurred_at=event.occurred_at,
                    driver_number=str(driver_number),
                    observation=LapObservation(**values),
                )
            )
        return cls(tuple(observations))

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
                occurred_at=(
                    item.observation.pit_occurred_at or item.occurred_at
                ),
                driver_number=item.driver_number,
                lap=item.observation.lap,
                previous_compound=item.observation.previous_compound,
                new_compound=item.observation.new_compound,
                stop_duration=item.observation.stop_duration,
                pit_lane_duration=item.observation.pit_lane_duration,
            )
            for item in self.lap_observations
            if item.driver_number == str(driver_number)
            and item.observation.pit_in is True
            and (event_limit is None or item.sequence <= event_limit)
            and (cutoff is None or parse_timestamp(item.occurred_at) <= cutoff)
        )
