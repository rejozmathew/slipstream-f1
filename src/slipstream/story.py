"""A deterministic, evidence-timed story ledger shared by replay and live.

The ledger is accumulated alongside canonical state, never by a browser or an
LLM. Occurrence and publication are separate: an order observation is neutral
until subsequent source evidence corroborates an on-track pass. Earlier events
are immutable; confirmation supersedes them only at the confirming cursor.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from typing import Any

from .events import NormalizedEvent, parse_timestamp
from .lifecycle import is_circulating, is_in_pit, is_stopped, terminal_state
from .state import DriverState, RaceState

STORY_MODEL_VERSION = "causal-story-v1"
PASS_CONFIRM_SECONDS = 5.0
STORY_PAGE_SIZE = 80


def _seconds(value: str) -> float:
    return parse_timestamp(value).timestamp()


def _fingerprint(event: NormalizedEvent) -> str:
    value = json.dumps(
        [event.kind, event.occurred_at, event.payload],
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(value.encode()).hexdigest()[:20]


def _lap_seconds(value: str | float | None) -> float | None:
    if value is None:
        return None
    try:
        parts = str(value).split(":")
        return sum(float(part) * 60 ** index for index, part in enumerate(reversed(parts)))
    except (TypeError, ValueError):
        return None


def _numeric_gap(value: str | None) -> float | None:
    if value is None or re.search(r"\bLAP", value, re.IGNORECASE):
        return None
    try:
        return float(value.lstrip("+"))
    except (TypeError, ValueError):
        return None


def _name(state: RaceState, number: str) -> str:
    driver = state.drivers.get(number)
    return (driver.code or driver.name or number) if driver else number


def _running(driver: DriverState) -> bool:
    return is_circulating(driver) and not is_in_pit(driver) and driver.activity != "IN_PIT"


def race_pair_eligible(state: RaceState, ahead: DriverState, behind: DriverState) -> bool:
    """Strict presentation/story eligibility; unknown is not green running."""
    return bool(
        state.session.layout_family == "race"
        and state.session.status == "RUNNING"
        and state.session.display_status == "GREEN"
        and state.session.lap is not None and state.session.lap >= 3
        and _running(ahead) and _running(behind)
        and ahead.lap is not None and ahead.lap == behind.lap
        and ahead.position is not None and behind.position is not None
    )


@dataclass(frozen=True)
class StoryEvent:
    id: str
    session_key: str
    kind: str
    occurred_at: str
    available_at: str
    available_sequence: int
    drivers: tuple[str, ...]
    title: str
    detail: str
    priority: int
    lap: int | None
    phase: str | None
    cause: str | None = None
    state: str = "confirmed"
    supersedes: str | None = None
    evidence: tuple[tuple[int, str, tuple[str, ...]], ...] = ()
    data: dict[str, Any] = field(default_factory=dict)

    def serialize(self) -> dict[str, Any]:
        return {
            "id": self.id, "sessionKey": self.session_key, "kind": self.kind,
            "occurredAt": self.occurred_at, "availableAt": self.available_at,
            "availableSequence": self.available_sequence,
            "driverNumbers": list(self.drivers), "cause": self.cause,
            "state": self.state, "supersedes": self.supersedes,
            "priority": self.priority, "lap": self.lap, "phase": self.phase,
            "title": self.title, "detail": self.detail,
            "evidence": [
                {"sequence": seq, "occurredAt": at, "fields": list(fields)}
                for seq, at, fields in self.evidence
            ],
            "data": dict(self.data),
        }


@dataclass(frozen=True)
class PendingPass:
    observation: StoryEvent
    ahead: str
    behind: str
    seen_ahead: bool = False
    seen_behind: bool = False


@dataclass(frozen=True)
class StoryEvidence:
    """Immutable reduction state. Full preparation and incremental live use it."""

    events: tuple[StoryEvent, ...] = ()
    previous: RaceState = field(default_factory=RaceState, repr=False, compare=False)
    order: tuple[str, ...] = ()
    pending: tuple[PendingPass, ...] = ()
    pit_entries: dict[str, tuple[str, str | None, str | None]] = field(default_factory=dict)
    battle_runs: dict[str, tuple[int, int]] = field(default_factory=dict)
    result_seen: bool = False

    def advance(self, event: NormalizedEvent, state: RaceState, sequence: int) -> StoryEvidence:
        before = self.previous
        timestamp = event.occurred_at
        session = state.session
        race = session.layout_family == "race"
        new: list[StoryEvent] = []
        fingerprint: str | None = None
        phase = session.qualifying_phase if session.qualifying_phase != "UNKNOWN" else None

        def emit(
            kind: str, title: str, detail: str = "", *, drivers: tuple[str, ...] = (),
            priority: int = 1, cause: str | None = None, status: str = "confirmed",
            occurred_at: str | None = None, supersedes: StoryEvent | None = None,
            data: dict[str, Any] | None = None,
        ) -> StoryEvent:
            nonlocal fingerprint
            if fingerprint is None:
                fingerprint = _fingerprint(event)
            identity = f"{session.key}:{fingerprint}:{kind}:{','.join(drivers)}"
            item = StoryEvent(
                id=hashlib.sha256(identity.encode()).hexdigest()[:24],
                session_key=str(session.key or "unknown"), kind=kind,
                occurred_at=occurred_at or timestamp, available_at=timestamp,
                available_sequence=sequence, drivers=drivers, title=title, detail=detail,
                priority=priority, lap=session.lap if race else None, phase=phase,
                cause=cause, state=status, supersedes=supersedes.id if supersedes else None,
                evidence=(supersedes.evidence if supersedes else ()) + (
                    (sequence, timestamp, tuple(sorted(event.payload.keys()))),
                ), data=data or {},
            )
            new.append(item)
            return item

        # Session axes are already authored by RaceState. Never derive a restart
        # from a race-control string, sector progress, or a marshal green flag.
        if event.kind == "session":
            flag = session.display_status
            if flag != before.session.display_status and flag != "UNKNOWN" and (before.session.display_status != "UNKNOWN" or flag != "GREEN"):
                label = {"VSC": "Virtual safety car", "VSC_ENDING": "VSC ending",
                         "SAFETY_CAR": "Safety car", "RED_FLAG": "Red flag",
                         "CHEQUERED": "Chequered flag", "GREEN": "Green flag",
                         "YELLOW": "Yellow flag", "RED": "Red flag"}.get(flag, flag.replace("_", " ").title())
                emit("FLAG", label, "Official whole-track status", priority=3 if flag in {"RED_FLAG", "RED", "VSC", "SAFETY_CAR", "CHEQUERED"} else 2,
                     cause=flag, data={"flag": flag})
            if phase and phase != before.session.qualifying_phase and before.session.qualifying_phase != "UNKNOWN":
                emit("PHASE", f"{phase} begins", "Source-confirmed segment change", priority=2, data={"phase": phase})
            if session.status == "RUNNING" and before.session.status == "SUSPENDED":
                emit("RESTART", "Session resumed", "Official session restart", priority=3)
            if not race and session.status == "FINISHED" and before.session.status != "FINISHED":
                emit("SESSION_END", f"{phase or session.name or 'Session'} flag shown",
                     "Laps already in progress may still change the order.", priority=3, status="provisional")

        if event.kind == "race_control":
            message = str(event.payload.get("message") or "").strip()
            if message and not any(m.message == message and m.occurred_at == timestamp for m in before.race_control):
                category = str(event.payload.get("category") or "Race control")
                num = event.payload.get("driver_number")
                kind = "LAP_DELETED" if "DELETED" in message.upper() else "PENALTY" if "PENALTY" in message.upper() else "RACE_CONTROL"
                emit(kind, "Lap deleted" if kind == "LAP_DELETED" else "Penalty notice" if kind == "PENALTY" else "Race control",
                     message, drivers=(str(num),) if num is not None else (), priority=2 if kind != "RACE_CONTROL" else 1,
                     cause="OFFICIAL_MESSAGE", data={"category": category})

        if event.kind == "weather" and state.weather.rainfall is not None and before.weather.rainfall is not None and state.weather.rainfall != before.weather.rainfall:
            emit("WEATHER", "Rain detected" if state.weather.rainfall else "Rain sensor now clear",
                 "Weather-feed observation; track grip is not inferred.", priority=2)

        number = str(event.payload.get("number", ""))
        driver = state.drivers.get(number)
        old = before.drivers.get(number)
        entries = self.pit_entries
        race_has_started = not race or (
            session.status in {"RUNNING", "FINISHED", "SUSPENDED"}
            and (not session.started_at or _seconds(timestamp) >= _seconds(session.started_at))
        )
        if driver and event.kind in {"timing", "driver"} and race_has_started:
            if old and is_in_pit(driver) and not is_in_pit(old) and _running(old):
                entries = dict(entries)
                entries[number] = (timestamp, old.compound, None)
                emit("PIT_IN", f"{_name(state, number)} enters the pit lane",
                     f"From P{old.position}" if old.position is not None else "Pit entry observed",
                     drivers=(number,), priority=2, cause="PIT", data={"position": old.position, "previousCompound": old.compound})
            pit_observation = event.payload.get("pit_observation") or {}
            if number in entries and (("compound" in event.payload and driver.compound and driver.compound != entries[number][1]) or pit_observation.get("new_compound")):
                entries = dict(entries)
                at, compound, _ = entries[number]
                entries[number] = (at, compound, pit_observation.get("new_compound") or driver.compound)
            if old and is_in_pit(old) and not is_in_pit(driver) and _running(driver):
                entry = entries.get(number)
                observed = entry[2] if entry else None
                emit("PIT_EXIT", f"{_name(state, number)} leaves the pit lane",
                     f"On {observed.lower()} tyres" if observed else "New tyre compound not yet confirmed",
                     drivers=(number,), priority=2, cause="PIT",
                     data={"position": driver.position, "previousCompound": entry[1] if entry else None, "compound": observed})
                entries = dict(entries)
                entries.pop(number, None)
            if old and driver.source_condition == "STOPPED" and old.source_condition != "STOPPED":
                emit("STOPPED", f"{_name(state, number)} stopped", "Source reports STOPPED; this is not a retirement.", drivers=(number,), priority=3, cause="STOPPED")
            elif old and is_stopped(old) and _running(driver):
                emit("RUNNING", f"{_name(state, number)} running again", "Positive source progress after a stop", drivers=(number,), priority=2)
            if old and terminal_state(driver) and terminal_state(driver) != terminal_state(old):
                final = terminal_state(driver)
                if final != "FINISHED":
                    emit("CLASSIFICATION", f"{_name(state, number)} classified {final}", "Source classification", drivers=(number,), priority=2, cause="CLASSIFICATION")
            elif old and driver.source_condition == "RETIRED_INDICATED" and old.source_condition != "RETIRED_INDICATED":
                emit("RETIRED_INDICATED", f"{_name(state, number)} reported retired", "Source indication; final classification is pending.", drivers=(number,), priority=2, status="provisional")

            # Only completed-lap evidence can create an improvement, not a later
            # result packet containing a historical best time.
            observation = event.payload.get("lap_observation")
            if isinstance(observation, dict) and observation.get("duration") is not None:
                lap_time = float(observation["duration"])
                prior = _lap_seconds(old.best_lap) if old else None
                invalid = observation.get("lap_validity") == "INVALID"
                if not invalid and (prior is None or lap_time < prior):
                    times = [_lap_seconds(d.best_lap) for d in before.drivers.values()]
                    known = [t for t in times if t is not None]
                    fastest = bool(known and lap_time < min(known))
                    if prior is not None or fastest:
                        emit("LAP_IMPROVEMENT", f"{_name(state, number)} sets {'the fastest lap' if fastest else 'a personal best'}",
                             f"{int(lap_time // 60)}:{lap_time % 60:06.3f} · lap {observation.get('lap', '—')}",
                             drivers=(number,), priority=2 if fastest else 1,
                             data={"lapTime": lap_time, "lap": observation.get("lap"), "sessionBest": fastest})

        # Expire candidates on caution, pit/lifecycle changes, lap mismatch or
        # reversed order. Both drivers must supply fresh progress after the
        # confirmation interval; mere silence never confirms an overtake.
        pending: list[PendingPass] = []
        for candidate in self.pending:
            a = state.drivers.get(candidate.ahead)
            b = state.drivers.get(candidate.behind)
            if not a or not b or not race_pair_eligible(state, a, b) or a.position >= b.position:
                continue
            elapsed = _seconds(timestamp) - _seconds(candidate.observation.available_at)
            if elapsed > 30:
                continue
            corroborates = event.kind == "timing" and bool(set(event.payload) & {"position", "lap", "track_position", "lap_observation"})
            current = replace(candidate,
                seen_ahead=candidate.seen_ahead or (elapsed >= PASS_CONFIRM_SECONDS and corroborates and number == a.number),
                seen_behind=candidate.seen_behind or (elapsed >= PASS_CONFIRM_SECONDS and corroborates and number == b.number))
            if current.seen_ahead and current.seen_behind:
                emit("PASS", f"{_name(state, a.number)} passes {_name(state, b.number)}",
                     f"Confirmed on-track change for P{a.position}", drivers=(a.number, b.number),
                     priority=3 if a.position == 1 else 2, cause="ON_TRACK",
                     occurred_at=current.observation.occurred_at, supersedes=current.observation,
                     data={"position": a.position})
            elif elapsed <= 30:
                pending.append(current)

        order = self.order
        if race and event.kind in {"timing", "driver"} and "position" in event.payload:
            ordered = sorted((d for d in state.drivers.values() if d.position is not None), key=lambda d: d.position)
            positions = [d.position for d in ordered]
            if len(set(positions)) == len(positions):
                latest = tuple(d.number for d in ordered)
                if order and set(latest) == set(order) and session.lap and session.lap >= 2:
                    old_indexes = {n: i for i, n in enumerate(order)}
                    new_indexes = {n: i for i, n in enumerate(latest)}
                    for n in latest:
                        if new_indexes[n] >= old_indexes[n]:
                            continue
                        crossed = [m for m in order[:old_indexes[n]] if new_indexes[m] > new_indexes[n]]
                        a = state.drivers[n]
                        for m in crossed:
                            b = state.drivers[m]
                            recent_pit = any(e.kind in {"PIT_IN", "PIT_EXIT"} and (n in e.drivers or m in e.drivers) and 0 <= _seconds(timestamp) - _seconds(e.available_at) <= 45 for e in (*self.events[-60:], *new))
                            cause = "CLASSIFICATION" if session.status == "FINISHED" or terminal_state(a) or terminal_state(b) else "PIT" if is_in_pit(a) or is_in_pit(b) or m in entries or recent_pit else "STOPPED" if is_stopped(b) or b.source_condition == "RETIRED_INDICATED" else None
                            item = emit("ORDER_CHANGE", f"{_name(state, n)} moves ahead of {_name(state, m)}",
                                        f"Now P{a.position}" + (" · pit-related order change" if cause == "PIT" else " · classification change" if cause == "CLASSIFICATION" else ""),
                                        drivers=(n, m), priority=2 if a.position == 1 else 1,
                                        cause=cause, status="confirmed" if cause else "provisional",
                                        data={"position": a.position})
                            if cause is None and race_pair_eligible(state, a, b):
                                pending.append(PendingPass(item, n, m))
                order = latest

        # A battle is sustained completed-lap evidence, reset by any caution.
        runs = self.battle_runs
        if session.display_status != "GREEN" or session.status != "RUNNING":
            runs = {}
        observation = event.payload.get("lap_observation")
        if race and driver and isinstance(observation, dict):
            ahead = next((d for d in state.drivers.values() if driver.position and d.position == driver.position - 1), None)
            gap = _numeric_gap(driver.interval_to_ahead)
            key = f"{ahead.number}:{driver.number}" if ahead else ""
            runs = {k: v for k, v in runs.items() if not k.endswith(":" + driver.number) or k == key}
            if ahead and race_pair_eligible(state, ahead, driver) and gap is not None and 0 <= gap <= 1:
                lap = int(observation.get("lap") or 0)
                count, last_lap = runs.get(key, (0, -1))
                count = count + 1 if lap == last_lap + 1 else 1 if lap != last_lap else count
                runs[key] = (count, lap)
                if count == 3 and lap != last_lap:
                    emit("BATTLE", f"{_name(state, driver.number)} within a second of {_name(state, ahead.number)}",
                         "Three consecutive completed laps in green running", drivers=(ahead.number, driver.number), priority=2,
                         data={"gapSeconds": gap, "position": driver.position})
            elif key:
                runs.pop(key, None)

        result_seen = self.result_seen
        if race:
            leaders = [d for d in state.drivers.values() if d.position == 1]
            winner = leaders[0] if len(leaders) == 1 and terminal_state(leaders[0]) == "FINISHED" else None
            prior_result = next((item for item in reversed(self.events) if item.kind in {"RESULT", "RESULT_CORRECTION"}), None)
            if winner and (session.control_status == "CHEQUERED" or session.status == "FINISHED") and (
                not result_seen or prior_result and prior_result.drivers != (winner.number,)
            ):
                emit("RESULT_CORRECTION" if result_seen else "RESULT", f"Provisional result updated: {_name(state, winner.number)} leads" if result_seen else f"{_name(state, winner.number)} wins on the road",
                     "Provisional classification · subject to official confirmation.", drivers=(winner.number,), priority=3,
                     status="corrected" if result_seen else "provisional", cause="CLASSIFICATION" if result_seen else "CHEQUERED",
                     supersedes=prior_result, data={"position": 1})
                result_seen = True

        return StoryEvidence(self.events + tuple(new), state, order, tuple(pending), entries, runs, result_seen)

    def snapshot(self, sequence: int, as_of: str | None, *, limit: int | None = STORY_PAGE_SIZE, offset: int = 0) -> dict[str, Any]:
        cutoff = _seconds(as_of) if as_of else float("-inf")
        available = [e for e in self.events if e.available_sequence <= sequence and _seconds(e.available_at) <= cutoff]
        superseded = {e.supersedes for e in available if e.supersedes}
        visible = [e for e in available if e.id not in superseded]
        # Preserve history order at equal timestamps with the evidence sequence.
        visible.sort(key=lambda e: (_seconds(e.available_at), e.available_sequence, e.id))
        results = [e for e in available if e.kind in {"RESULT", "RESULT_CORRECTION"}]
        total = len(visible)
        offset = max(0, offset)
        end = max(0, total - offset)
        start = max(0, end - limit) if limit is not None else 0
        page = visible[start:end]
        return {
            "modelVersion": STORY_MODEL_VERSION, "sequence": sequence, "asOf": as_of,
            "revision": hashlib.sha256("|".join(e.id for e in visible).encode()).hexdigest()[:16],
            "events": [e.serialize() for e in page], "total": total,
            "hasMore": start > 0, "nextOffset": offset + len(page),
            "result": {"state": "provisional" if results else "none", "since": results[0].available_at if results else None},
        }
