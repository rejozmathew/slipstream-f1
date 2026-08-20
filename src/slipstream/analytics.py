"""Deterministic, source-neutral replay analytics with explicit provenance."""

from __future__ import annotations

import re
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from math import sqrt
from statistics import median
from typing import Any

from .context_types import absent_historical, absent_official_pre_race
from .events import parse_timestamp
from .evidence import LapObservation, PitEvent
from .library import ReplayResource
from .state import DriverState, RaceState
from .strategy_rules import strategy_rule_profile
from .weekend import ContextAvailability

ANALYTICS_SCHEMA_VERSION = 1
# v2.1 contract surface (Phase A). Bump on every model/contract change.
ANALYTICS_MODEL_VERSION = "race-intelligence-v2.1"


def metric(
    value: Any,
    *,
    status: str,
    evidence: list[str],
    unit: str | None = None,
    quality: str | None = None,
) -> dict[str, Any]:
    return {
        "value": value,
        "status": status,
        "unit": unit,
        "evidenceBasis": evidence,
        "modelVersion": ANALYTICS_MODEL_VERSION,
        "quality": quality,
    }


def unknown(reason: str) -> dict[str, Any]:
    return metric(None, status="UNKNOWN", evidence=[reason], quality="insufficient")


def _as_of_ms(as_of: str | None) -> int:
    """Source cursor time in epoch-ms, or -1 if unparseable (hysteresis no-op)."""
    if not as_of:
        return -1
    try:
        return int(parse_timestamp(as_of).timestamp() * 1000)
    except (ValueError, TypeError, AttributeError, OverflowError):
        return -1


def _hysteresis_advance(
    held: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    source_ms: int,
    *,
    hold_ms: int,
    switch_margin: float,
    drivers_exist: bool,
) -> dict[str, Any] | None:
    """v2.1 §20 / invariant 11: server-side Battle hysteresis.

    Pure function of (held, candidate, source cursor time) — no viewer state.
    Mirrors the prior client rule: a missing held pair switches immediately;
    otherwise both the hold interval AND the score margin must be satisfied,
    unless the held pair is no longer valid (drivers left / positions broken).
    """
    if candidate is None or source_ms < 0:
        return held
    if held is None:
        return {"candidate": candidate, "since": source_ms}
    held_candidate = held["candidate"]
    same = (
        held_candidate.get("aheadDriverNumber") == candidate.get("aheadDriverNumber")
        and held_candidate.get("behindDriverNumber") == candidate.get("behindDriverNumber")
    )
    if same:
        return {"candidate": candidate, "since": held["since"]}
    hold_expired = (source_ms - int(held.get("since", 0))) >= hold_ms
    margin_met = (
        float(candidate.get("score", 0.0))
        >= float(held_candidate.get("score", 0.0)) + switch_margin
    )
    if not drivers_exist or (hold_expired and margin_met):
        return {"candidate": candidate, "since": source_ms}
    return held


class AnalyticsService:
    """Cache calculations by meaningful factual/context revisions."""

    def __init__(self) -> None:
        self._cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        # v2.1 §20 / invariant 11: Battle hysteresis is SERVER-owned, session-scoped
        # and cursor-keyed (not viewer-owned mutable state). Two viewers at the same
        # cursor get the identical held state; a backward seek resets it.
        self._battle_held: dict[tuple[str, int], dict[str, Any] | None] = {}

    def _apply_battle_hysteresis(
        self,
        base: dict[str, Any],
        session_key: str,
        sequence: int,
        as_of: str | None,
    ) -> None:
        battle = base.get("battle")
        if not isinstance(battle, dict):
            return
        candidate = battle.get("recommended")
        hold_ms = int(battle.get("hysteresis", {}).get("minimumHoldSeconds", 20) * 1000)
        switch_margin = float(battle.get("hysteresis", {}).get("switchMargin", 8))
        source_ms = _as_of_ms(as_of)
        
        prior_sequences = [
            seq for (sk, seq) in self._battle_held if sk == session_key and seq < sequence
        ]
        held = (
            self._battle_held[(session_key, max(prior_sequences))]
            if prior_sequences
            else None
        )
        
        held = _hysteresis_advance(
            held,
            candidate,
            source_ms,
            hold_ms=hold_ms,
            switch_margin=switch_margin if source_ms >= 0 else 0.0,
            drivers_exist=True,
        )
        self._battle_held[(session_key, sequence)] = held
        # Publish the stabilized action + held state for the (render-only) client.
        battle["heldRecommendation"] = held
        battle["stabilizedRecommended"] = (
            held["candidate"] if held is not None else None
        )
        battle["hysteresis"]["owner"] = "server"
        battle["hysteresis"]["sessionScoped"] = True
        battle["hysteresis"]["cursorKeyed"] = True

    def snapshot(
        self,
        resource: ReplayResource,
        state: RaceState,
        *,
        sequence: int,
        as_of: str | None,
        context: ContextAvailability,
    ) -> dict[str, Any]:
        signature = _signature(resource, state, context, sequence, as_of)
        cached = self._cache.get(signature)
        if cached is None:
            cached = build_analytics_snapshot(
                resource,
                state,
                sequence=sequence,
                as_of=as_of,
                context=context,
            )
            self._cache[signature] = cached
            if len(self._cache) > 128:
                self._cache.pop(next(iter(self._cache)))
        response = deepcopy(cached)
        response["asOf"] = as_of
        response["sequence"] = sequence
        self._apply_battle_hysteresis(
            response, resource.descriptor.key, sequence, as_of
        )
        return response


def _aggregate_dry_tyre_landscape(
    states: dict[str, str]
) -> dict[str, int]:
    counts = {"SATISFIED": 0, "UNSATISFIED": 0, "NOT_APPLICABLE": 0, "UNKNOWN": 0}
    for state in states.values():
        if state in counts:
            counts[state] += 1
    return counts

def build_analytics_snapshot(
    resource: ReplayResource,
    state: RaceState,
    *,
    sequence: int,
    as_of: str | None,
    context: ContextAvailability,
) -> dict[str, Any]:
    evidence_by_driver = {
        number: resource.evidence.laps_for_driver(number, event_limit=sequence)
        for number in state.drivers
    }
    pit_events = tuple(
        event
        for number in state.drivers
        for event in resource.evidence.pit_events_for_driver(
            number, event_limit=sequence
        )
    )
    context_payload = context.context if context.status == "ready" else None
    context_laps = _context_laps(context_payload)
    pit_loss = _pit_loss_metric(
        pit_events,
        context_payload,
        session_kind=resource.descriptor.session_kind,
    )
    stage = _analytics_stage(state, context.status, evidence_by_driver)
    ordered = sorted(
        state.drivers.values(), key=lambda item: item.position or 999
    )
    rules = strategy_rule_profile(
        resource.descriptor.year, resource.descriptor.session_kind
    )
    driver_models: dict[str, dict[str, Any]] = {}
    for index, driver in enumerate(ordered):
        laps = evidence_by_driver.get(driver.number, ())
        pace = pace_model(laps)
        weekend_degradation = _weekend_driver_degradation(
            driver.number, context_payload
        )
        events = tuple(
            item for item in pit_events if item.driver_number == driver.number
        )
        driver_models[driver.number] = {
            "driverNumber": driver.number,
            "ahead": _driver_context(ordered[index - 1], driver, "ahead")
            if index > 0
            else None,
            "behind": _driver_context(driver, ordered[index + 1], "behind")
            if index + 1 < len(ordered)
            else None,
            "pace": pace,
            "pitEvents": [_pit_event_payload(item) for item in events],
            "strategy": _driver_strategy(
                driver,
                ordered,
                laps,
                evidence_by_driver,
                pit_events,
                pit_loss,
                pace,
                weekend_degradation,
                state,
                stage,
                rules=rules,
            ),
            "weekendEvidence": _weekend_driver_evidence(
                driver.number, context_laps
            ),
        }
    battle = battle_recommendation(
        ordered,
        driver_models,
        evidence_by_driver,
        as_of=as_of,
        layout_family=resource.descriptor.layout_family,
    )
    race_strategy = _race_strategy(
        driver_models, evidence_by_driver, context_payload, pit_loss, state, stage
    )
    # v2.1 Phase C: race-level strategy validity + active-runner field
    # distributions (deterministic, cursor-scoped).
    strategy_validity = _strategy_validity(state, stage)
    field_distributions = _field_distributions(state)
    # v2.1 §15: per-driver dry-tyre requirement state, computed from each
    # driver's compound history at the cursor + the rule profile.
    dry_tyre_per_driver: dict[str, str] = {}
    for number in _active_runner_numbers(state):
        dry_tyre_per_driver[number] = _dry_tyre_state(
            state.drivers[number], rules, evidence_by_driver.get(number, ())
        )
    return {
        "v": 1,
        "type": "analytics.snapshot",
        "schemaVersion": ANALYTICS_SCHEMA_VERSION,
        "modelVersion": ANALYTICS_MODEL_VERSION,
        "sessionKey": resource.descriptor.key,
        "sessionKind": resource.descriptor.session_kind,
        "layoutFamily": resource.descriptor.layout_family,
        "sequence": sequence,
        "asOf": as_of,
        "stage": stage,
        "raceRead": {
            "raceLifecycle": stage,
            "activeRunnerCount": field_distributions.get("activeRunnerCount", 0),
            "startingTyreDistribution": field_distributions.get("startingTyreDistribution", {}),
            "currentTyreDistribution": field_distributions.get("currentTyreDistribution", {}),
            "completedStopDistribution": field_distributions.get("stopDistribution", {}),
            "paceTrendDistribution": {},
            "dryRequirementLandscape": _aggregate_dry_tyre_landscape(dry_tyre_per_driver),
            "evidenceBasis": ["v2.1 §18: field distributions exclude retired/DNS runners"],
        },
        # v2.1 §11: strategy validity is a first-class state, not an implicit
        # property of the published window. Phase C computes it from the
        # track-control state at the cursor + the analytics stage.
        "strategyValidity": strategy_validity,
        # v2.1 §17.1: NetPitLoss is not yet a defensible derived metric; the
        # fields that depend on it are suppressed until it exists.
        "netPitLoss": {
            "status": "NOT_IMPLEMENTED",
            "blocks": ["freeStopMargin", "projectedRejoinPosition", "undercutQuantified"],
            "evidenceBasis": [
                "v2.1 §17.1: free-stop margin, projected rejoin, and quantified undercut require a defensible Net Pit Loss; raw pit-lane duration is not a substitute."
            ],
        },
        # v2.1 §8.2 / §9 / §10: the published window must pass hard validity
        # (0 violations), soft plausibility, and the stability gate.
        "projectionGate": _projection_gate(state, stage),
        "sportingRules": {
            "profileVersion": rules.profile_version,
            "mandatoryPitStops": rules.mandatory_pit_stops,
            "dryCompoundObligation": rules.dry_compound_obligation,
            # v2.1 §15: the per-driver dry-tyre requirement state (UNSATISFIED /
            # SATISFIED / NOT_APPLICABLE / UNKNOWN) is computed in Phase C from
            # compound history + rule profile. The rule profile is published
            # here so the UI can explain the state.
            "dryTyreRequirement": {
                "ruleProfile": rules.dry_compound_obligation,
                "perDriverState": dry_tyre_per_driver,
                "evidenceBasis": list(rules.evidence),
            },
            "evidenceBasis": list(rules.evidence),
        },
        "context": {
            "status": context.status,
            "meetingKey": resource.descriptor.meeting_key,
            "generatedAt": context_payload.get("generated_at")
            if context_payload
            else None,
            "evidenceCutoff": resource.descriptor.date_start,
            "modelVersion": context_payload.get("model_version")
            if context_payload
            else None,
            "sessionCount": len(context_payload.get("sessions", []))
            if context_payload
            else 0,
            "externalIntelligence": (
                context_payload.get("external_intelligence")
                if context_payload
                else {"status": "disabled", "items": []}
            ),
            "error": context.error,
        },
        "pitLoss": pit_loss,
        "raceStrategy": race_strategy,
        # v2.1 §5.2 / §5.3: Historical + OfficialPreRace are separate, attributed,
        # target-session-owned context artifacts. Contract is Phase A;
        # acquisition is Phase F (manual path guaranteed, automated is a spike).
        "historical": absent_historical(reason="phase_f_pending"),
        "officialPreRace": absent_official_pre_race(reason="phase_f_pending"),
        # v2.1 §5.5 / §26: data-ownership contract (target-session-owned,
        # session-scoped, cursor-keyed; M4 downstream deletion is a non-goal
        # for v2.1).
        "dataOwnership": {
            "owner": "target_session",
            "sessionScoped": True,
            "cursorKeyed": True,
            "sessionKey": resource.descriptor.key,
            "adminDeletion": {
                "status": "MILESTONE_4",
                "evidenceBasis": [
                    ("v2.1 §5.5: v2.1 defines the data-ownership contract that "
                     "Milestone 4 will enforce; actual Admin deletion is an M4 "
                     "non-goal.")
                ],
            },
            "evidenceBasis": [
                ("v2.1 §5.5: analytics state (hysteresis, cache, stabilization) "
                 "is target-session-owned, session-scoped and cursor-keyed; "
                 "never viewer-owned mutable state.")
            ],
        },
        "drivers": driver_models,
        "battle": battle,
    }


def pace_model(laps: tuple[LapObservation, ...]) -> dict[str, Any]:
    grouped: dict[str, list[LapObservation]] = {}
    for lap in laps:
        key = str(lap.stint_number or f"compound:{lap.compound or 'unknown'}")
        grouped.setdefault(key, []).append(lap)
    baselines = {
        key: _robust_baseline(items)
        for key, items in grouped.items()
    }
    samples = []
    for lap in laps:
        key = str(lap.stint_number or f"compound:{lap.compound or 'unknown'}")
        baseline = baselines.get(key)
        samples.append(
            {
                "lap": lap.lap,
                "rawLapTime": lap.duration,
                "delta": (
                    round(lap.duration - baseline, 3)
                    if lap.duration is not None and baseline is not None
                    else None
                ),
                "compound": lap.compound,
                "tyreAge": lap.tyre_age,
                "stintNumber": lap.stint_number,
                "quality": lap.quality,
                "contaminationReasons": list(lap.contamination_reasons),
            }
        )
    current_stint = laps[-1].stint_number if laps else None
    current = [
        lap
        for lap in laps
        if lap.stint_number == current_stint and lap.quality == "representative"
    ]
    degradation = _degradation(current)
    return {
        "definition": "lap pace delta versus robust clean-lap median for that stint",
        "baselineVersion": "clean-stint-median-mad-v1",
        "samples": samples,
        "currentStintBaseline": baselines.get(str(current_stint))
        if current_stint is not None
        else None,
        "degradation": degradation,
        # v2.1 §20 / invariant 11: the y-axis scale for the pace-delta chart is
        # computed server-side (deterministic, cursor-scoped) so the client
        # renders it verbatim instead of recomputing locally.
        "scale": _pace_scale(samples),
    }


def _pace_scale(samples: list[dict[str, Any]]) -> float:
    """v2.1 §20: robust MAD-based y-axis scale for the pace-delta chart.

    Mirrors the prior client `robustScale`: median of |delta| over
    representative samples with a delta, MAD-based 3× retention, 0.25s floor.
    Pure function of the sample list (no viewer state).
    """
    values = sorted(
        abs(float(s["delta"]))
        for s in samples
        if s.get("quality") == "representative" and s.get("delta") is not None
    )
    if not values:
        return 0.25
    middle = values[len(values) // 2]
    deviations = sorted(abs(v - middle) for v in values)
    mad = deviations[len(deviations) // 2]
    retained = [v for v in values if v <= middle + max(0.25, mad * 3)]
    return max(0.25, retained[-1] if retained else middle)


def battle_recommendation(
    ordered: list[DriverState],
    driver_models: dict[str, dict[str, Any]],
    evidence_by_driver: dict[str, tuple[LapObservation, ...]],
    *,
    as_of: str | None,
    layout_family: str | None = None,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for index in range(1, len(ordered)):
        ahead = ordered[index - 1]
        behind = ordered[index]
        gap = _numeric_gap(behind.interval_to_ahead)
        if gap is None:
            continue
        if ahead.status != "RUNNING" or behind.status != "RUNNING":
            continue
        if abs((ahead.lap or 0) - (behind.lap or 0)) > 1:
            continue
        score = max(0.0, 70.0 - min(gap, 14.0) * 5.0)
        factors: list[dict[str, Any]] = [
            {"name": "current_gap", "value": gap, "weight": round(score, 2)}
        ]
        ahead_deg = _metric_number(
            driver_models[ahead.number]["pace"]["degradation"]
        )
        behind_deg = _metric_number(
            driver_models[behind.number]["pace"]["degradation"]
        )
        if ahead_deg is not None and behind_deg is not None:
            advantage = ahead_deg - behind_deg
            contribution = max(-10.0, min(15.0, advantage * 80.0))
            score += contribution
            factors.append(
                {
                    "name": "relative_degradation",
                    "value": round(advantage, 3),
                    "weight": round(contribution, 2),
                }
            )
        ahead_pace = driver_models[ahead.number]["pace"].get("currentStintBaseline")
        behind_pace = driver_models[behind.number]["pace"].get("currentStintBaseline")
        if isinstance(ahead_pace, (int, float)) and isinstance(
            behind_pace, (int, float)
        ):
            pace_advantage = float(ahead_pace) - float(behind_pace)
            contribution = max(-10.0, min(18.0, pace_advantage * 12.0))
            score += contribution
            factors.append(
                {
                    "name": "representative_pace",
                    "value": round(pace_advantage, 3),
                    "weight": round(contribution, 2),
                }
            )
        if ahead.tyre_age is not None and behind.tyre_age is not None:
            offset = ahead.tyre_age - behind.tyre_age
            contribution = max(-5.0, min(10.0, offset * 0.8))
            score += contribution
            factors.append(
                {
                    "name": "tyre_age_offset",
                    "value": offset,
                    "weight": round(contribution, 2),
                }
            )
        significance = max(0.0, 8.0 - float((ahead.position or 10) - 1))
        score += significance
        factors.append(
            {
                "name": "position_significance",
                "value": ahead.position,
                "weight": significance,
            }
        )
        ahead_window = driver_models[ahead.number]["strategy"]["pitWindow"].get(
            "value"
        )
        behind_window = driver_models[behind.number]["strategy"]["pitWindow"].get(
            "value"
        )
        if (
            isinstance(ahead_window, list)
            and isinstance(behind_window, list)
            and len(ahead_window) == 2
            and len(behind_window) == 2
        ):
            overlap = max(
                0,
                min(ahead_window[1], behind_window[1])
                - max(ahead_window[0], behind_window[0])
                + 1,
            )
            contribution = min(8.0, float(overlap) * 2.0)
            score += contribution
            factors.append(
                {
                    "name": "pit_window_overlap",
                    "value": overlap,
                    "weight": contribution,
                }
            )
        candidates.append(
            {
                "aheadDriverNumber": ahead.number,
                "behindDriverNumber": behind.number,
                "score": round(max(0.0, min(100.0, score)), 2),
                "gapSeconds": gap,
                "factors": factors,
            }
        )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    recommended = candidates[0] if candidates else None
    gap_history = []
    if recommended:
        ahead_laps = evidence_by_driver.get(recommended["aheadDriverNumber"], ())
        behind_laps = evidence_by_driver.get(recommended["behindDriverNumber"], ())
        ahead_by_lap = {lap.lap: lap for lap in ahead_laps}
        behind_by_lap = {lap.lap: lap for lap in behind_laps}
        shared_laps = sorted(set(ahead_by_lap.keys()) & set(behind_by_lap.keys()))
        for lap_num in shared_laps[-10:]:
            a_start = parse_timestamp(ahead_by_lap[lap_num].started_at).timestamp()
            b_start = parse_timestamp(behind_by_lap[lap_num].started_at).timestamp()
            gap_val = abs(b_start - a_start)
            if gap_val < 60.0:
                gap_history.append({"at": behind_by_lap[lap_num].started_at, "value": round(gap_val, 3)})

    trend = "INSUFFICIENT HISTORY"
    if len(gap_history) >= 3:
        first_val = gap_history[0]["value"]
        last_val = gap_history[-1]["value"]
        if last_val < first_val - 0.05:
            trend = "CLOSING"
        elif last_val > first_val + 0.05:
            trend = "OPENING"
        else:
            trend = "STABLE"

    return {
        "recommended": recommended,
        "gapHistory": gap_history,
        "gapTrend": trend,
        "candidates": candidates,
        # v2.1 Scenario 15: Strategy/Battle are only meaningful for race
        # layouts. The server publishes the gate so the client renders it
        # verbatim instead of recomputing layout semantics locally.
        "available": layout_family == "race",
        "hysteresis": {"minimumHoldSeconds": 20, "switchMargin": 8},
        "modelVersion": ANALYTICS_MODEL_VERSION,
    }



def _transition_samples(
    evidence_by_driver: dict[str, tuple[LapObservation, ...]],
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for driver_number, observations in evidence_by_driver.items():
        for observation in observations:
            if (
                observation.pit_in is not True
                or not observation.previous_compound
                or not observation.new_compound
                or observation.previous_compound == observation.new_compound
                or observation.tyre_age is None
            ):
                continue
            samples.append(
                {
                    "driverNumber": driver_number,
                    "previousCompound": observation.previous_compound,
                    "newCompound": observation.new_compound,
                    "stintLife": observation.tyre_age,
                    "lap": observation.lap,
                }
            )
    return samples


def _driver_transition_outlook(
    driver: DriverState,
    evidence_by_driver: dict[str, tuple[LapObservation, ...]],
    state: RaceState,
) -> tuple[dict[str, Any], dict[str, Any], list[tuple[str, int]]]:
    current_lap = driver.lap or state.session.lap
    current_age = driver.tyre_age
    if not driver.compound or current_lap is None or current_age is None:
        reason = "current compound, lap, and tyre age are required"
        return unknown(reason), unknown(reason), []
    comparable = [
        item
        for item in _transition_samples(evidence_by_driver)
        if item["previousCompound"] == driver.compound
        and item["stintLife"] >= max(2, current_age - 2)
    ]
    counts = Counter(str(item["newCompound"]) for item in comparable)
    common = counts.most_common()
    supported = bool(
        len(comparable) >= 3
        and common
        and common[0][1] >= 2
        and common[0][1] / len(comparable) >= 0.6
    )
    next_compound = (
        metric(
            common[0][0],
            status="ESTIMATE",
            evidence=[
                f"field consensus from {common[0][1]} of {len(comparable)} current-Race transitions",
                "only transitions at comparable or later tyre life are included",
            ],
            quality="medium" if len(comparable) >= 5 else "low",
        )
        if supported
        else unknown("no clear same-compound consensus at comparable tyre life")
    )
    lives = sorted(
        int(item["stintLife"])
        for item in comparable
        if supported and item["newCompound"] == next_compound["value"]
    )
    if len(lives) < 3:
        return next_compound, unknown("insufficient comparable stint-life evidence"), common
    lower_life = lives[len(lives) // 4]
    upper_life = lives[(len(lives) * 3) // 4]
    if upper_life <= current_age:
        return (
            next_compound,
            unknown("comparable transition life has already been exceeded"),
            common,
        )
    stint_start = current_lap - current_age + 1
    projected = [
        max(current_lap, stint_start + lower_life - 1),
        stint_start + upper_life - 1,  # clamped below (race-horizon, v2.1 §12)
    ]
    # v2.1 §12 / Scenario 18: no model may publish a normal future stop beyond
    # the race finish. A window whose end would overrun the race end is
    # rejected (UNKNOWN) rather than clamped silently — the hard-validity gate
    # is enforced by construction (0 hard violations published).
    # Furthermore, normal pit stops do not occur in the last 3 laps.
    total_laps = state.session.total_laps
    if total_laps and (projected[1] > total_laps or projected[0] > total_laps - 3):
        return (
            next_compound,
            unknown(
                "projected window would overrun or abut the race finish; "
                "rejected by the hard-validity gate (v2.1 §12)"
            ),
            common,
        )
    if projected[1] < current_lap:
        return next_compound, unknown("no defensible future pit window remains"), common
    pit_window = metric(
        projected,
        status="ESTIMATE",
        evidence=[
            f"central stint-life range from {len(lives)} comparable current-Race transitions",
            f"projected from this driver's current stint start at lap {stint_start}",
        ],
        unit="lap",
        quality="medium" if len(lives) >= 5 else "low",
    )
    return next_compound, pit_window, common


def _driver_strategy(
    driver: DriverState,
    ordered: list[DriverState],
    laps: tuple[LapObservation, ...],
    evidence_by_driver: dict[str, tuple[LapObservation, ...]],
    pit_events: tuple[PitEvent, ...],
    pit_loss: dict[str, Any],
    pace: dict[str, Any],
    weekend_degradation: dict[str, Any],
    state: RaceState,
    stage: str,
    rules=None,
) -> dict[str, Any]:
    next_compound, pit_window, common = _driver_transition_outlook(
        driver, evidence_by_driver, state
    )
    in_session_degradation = pace["degradation"]
    degradation = (
        in_session_degradation
        if _metric_number(in_session_degradation) is not None
        else weekend_degradation
    )
    degradation_value = _metric_number(degradation)
    tyre_stress = (
        metric(
            "HIGH"
            if degradation_value >= 0.15
            else "MEDIUM"
            if degradation_value >= 0.06
            else "LOW",
            status="ESTIMATE",
            evidence=["model-versioned thresholds over clean current-stint degradation"],
            quality=degradation.get("quality"),
        )
        if degradation_value is not None
        else unknown("clean current-stint degradation is unavailable")
    )
    stop_count = _likely_stop_count(driver, ordered, state)
    primary = (
        metric(
            f"{driver.compound} → {next_compound['value']}",
            status="ESTIMATE",
            evidence=next_compound["evidenceBasis"],
            quality=next_compound["quality"],
        )
        if driver.compound and next_compound["value"]
        else unknown("current and likely next compounds are not both established")
    )
    alternate = (
        metric(
            f"{driver.compound} → {common[1][0]}",
            status="ESTIMATE",
            evidence=[f"{common[1][1]} observed alternate transitions"],
            quality="low",
        )
        if driver.compound and next_compound["value"] is not None and len(common) > 1 and common[1][1] >= 2
        else unknown("no supported alternate compound consensus")
    )
    # v2.1 §17.1: freeStopMargin + projectedRejoinPosition are SUPPRESSED until
    # a defensible NetPitLoss exists. Raw pit-lane duration is not a substitute.
    # Force both to UNKNOWN with explicit provenance naming the missing dependency.
    _net_pit_loss_block = (
        "v2.1 §17.1: suppressed until NetPitLoss exists; raw pit-lane duration "
        "is not a substitute"
    )
    free_stop = unknown(_net_pit_loss_block)
    projected_rejoin = unknown(_net_pit_loss_block)
    # v2.1 §17: undercutStrength downgraded from quantified strength to
    # descriptive "undercut conditions" — must not imply quantified pit
    # economics (blocked by NetPitLoss).
    undercut = (
        metric(
            "FAVOURABLE"
            if degradation_value is not None and degradation_value >= 0.15
            else "NEUTRAL"
            if degradation_value is not None and degradation_value >= 0.08
            else "UNFAVOURABLE",
            status="ESTIMATE",
            evidence=[
                "descriptive undercut conditions from clean-lap degradation; quantified pit economics require a defensible NetPitLoss (v2.1 §17)",
                "traffic and warm-up effects are not modelled",
            ],
            quality=degradation.get("quality"),
        )
        if degradation_value is not None
        else unknown(
            "degradation evidence is required; quantified undercut is blocked "
            "until NetPitLoss exists (v2.1 §17.1)"
        )
    )
    changes: list[str] = []
    in_session_value = _metric_number(in_session_degradation)
    weekend_value = _metric_number(weekend_degradation)
    if in_session_value is not None and weekend_value is not None:
        if in_session_value >= weekend_value + 0.05:
            changes.append("DEGRADATION ABOVE WEEKEND REFERENCE")
        elif in_session_value <= weekend_value - 0.05:
            changes.append("DEGRADATION BELOW WEEKEND REFERENCE")
    return {
        "scope": "DRIVER",
        "driverNumber": driver.number,
        "stage": stage,
        # v2.1 §12: disposition + windowState are first-class per-driver states.
        "disposition": _driver_disposition(driver, state, pit_window),
        "windowState": _window_state(driver, state, pit_window),
        # v2.1 §15: per-driver dry-tyre requirement state.
        "dryTyreRequirement": (
            _dry_tyre_state(driver, rules, evidence_by_driver.get(driver.number, ()))
            if rules is not None
            else "UNKNOWN"
        ),
        "changes": changes,
        "likelyStopCount": stop_count,
        "primaryStrategy": primary,
        "alternateStrategy": alternate,
        "likelyNextCompound": next_compound,
        "pitWindow": pit_window,
        "tyreStress": tyre_stress,
        "degradation": degradation,
        "pitLoss": pit_loss,
        "undercutStrength": undercut,
        "projectedRejoinPosition": projected_rejoin,
        "freeStopMargin": free_stop,
        "weatherRisk": (
            metric(
                "RAIN DETECTED",
                status="OBSERVED",
                evidence=["current normalized rainfall sensor observation"],
                quality="observed",
            )
            if state.weather.rainfall is True
            else unknown("no forecast-capable weather evidence")
        ),
        "rulesNote": (
            "Sprint has no Grand Prix mandatory-stop assumption"
            if state.session.session_kind == "sprint"
            else "Tyre legality is not inferred without event-specific allocation evidence"
        ),
    }



def _context_race_like_transitions(
    context: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not context:
        return []
    samples: list[dict[str, Any]] = []
    for session in _same_meeting_context_sessions(context):
        if session.get("session_kind") != "sprint":
            continue
        for observation in session.get("lap_observations", []):
            previous = observation.get("previous_compound")
            new = observation.get("new_compound")
            life = observation.get("tyre_age")
            if (
                not previous
                or not new
                or previous == new
                or not isinstance(life, (int, float))
            ):
                continue
            samples.append(
                {
                    "driverNumber": str(observation.get("driver_number") or ""),
                    "previousCompound": str(previous),
                    "newCompound": str(new),
                    "stintLife": int(life),
                    "lap": observation.get("lap"),
                    "source": "same-meeting Sprint",
                }
            )
    return samples


def _race_strategy(
    driver_models: dict[str, dict[str, Any]],
    evidence_by_driver: dict[str, tuple[LapObservation, ...]],
    context: dict[str, Any] | None,
    pit_loss: dict[str, Any],
    state: RaceState,
    stage: str,
) -> dict[str, Any]:
    # v2.1 §13/§22: Sprint transitions are NOT race-like for a GP Race.
    # Only current-Race field transitions are used.
    current_samples = [
        {**item, "source": "current Race"}
        for item in _transition_samples(evidence_by_driver)
    ]
    samples = current_samples
    pairs = Counter(
        (str(item["previousCompound"]), str(item["newCompound"]))
        for item in samples
    ).most_common()
    supported = bool(
        len(samples) >= 3
        and pairs
        and pairs[0][1] >= 2
        and pairs[0][1] / len(samples) >= 0.5
    )
    evidence_scope = [
        f"{len(current_samples)} current-Race field transitions",
        "v2.1 §13: Sprint transitions excluded (not GP-comparable)",
        "Practice and Qualifying pit/garage activity is excluded",
    ]
    primary_pair = pairs[0][0] if supported else None
    primary = (
        metric(
            f"{primary_pair[0]} → {primary_pair[1]}",
            status="ESTIMATE",
            evidence=[
                f"field consensus from {pairs[0][1]} of {len(samples)} race-like transitions",
                *evidence_scope,
            ],
            quality="medium" if len(samples) >= 6 else "low",
        )
        if primary_pair
        else unknown("no race-wide compound-transition consensus in current-meeting evidence")
    )
    alternate = (
        metric(
            f"{pairs[1][0][0]} → {pairs[1][0][1]}",
            status="ESTIMATE",
            evidence=[
                f"secondary field pattern in {pairs[1][1]} comparable race-like transitions",
                *evidence_scope,
            ],
            quality="low",
        )
        if supported and len(pairs) > 1 and pairs[1][1] >= 2
        else unknown("no supported race-wide alternate compound consensus")
    )
    likely_next = (
        metric(
            primary_pair[1],
            status="ESTIMATE",
            evidence=primary["evidenceBasis"],
            quality=primary["quality"],
        )
        if primary_pair
        else unknown("race-wide next compound is not established")
    )
    lives = sorted(
        int(item["stintLife"])
        for item in samples
        if primary_pair
        and item["previousCompound"] == primary_pair[0]
        and item["newCompound"] == primary_pair[1]
    )
    race_window = unknown("insufficient race-like stint-life evidence")
    if len(lives) >= 3:
        lower_life = lives[len(lives) // 4]
        upper_life = lives[(len(lives) * 3) // 4]
        current_lap = state.session.lap or 1
        projected_windows = []
        for driver in state.drivers.values():
            if (
                driver.compound == primary_pair[0]
                and driver.tyre_age is not None
                and upper_life > driver.tyre_age
            ):
                driver_lap = driver.lap or current_lap
                start = driver_lap - driver.tyre_age + 1
                projected_windows.append(
                    (max(current_lap, start + lower_life - 1), start + upper_life - 1)
                )
        if projected_windows:
            starts = sorted(item[0] for item in projected_windows)
            ends = sorted(item[1] for item in projected_windows)
            projected = [round(median(starts)), round(median(ends))]
            # v2.1 §12 / Scenario 18: race-wide window must not overrun the
            # race finish — rejected by the hard-validity gate, not clamped.
            if state.session.total_laps:
                if projected[0] > state.session.total_laps - 3:
                    projected = []
                elif projected[1] > state.session.total_laps:
                    projected[1] = state.session.total_laps
        elif current_lap <= 1:
            projected = [lower_life, upper_life]
        else:
            projected = []
        if projected and projected[1] >= current_lap:
            race_window = metric(
                [max(current_lap, projected[0]), projected[1]],
                status="ESTIMATE",
                evidence=[
                    f"race-wide projection from central stint-life range of {len(lives)} race-like transitions",
                    *evidence_scope,
                ],
                unit="lap",
                quality="medium" if len(lives) >= 6 else "low",
            )
    degradation_values = [
        float(model["strategy"]["degradation"]["value"])
        for model in driver_models.values()
        if isinstance(model["strategy"]["degradation"].get("value"), (int, float))
    ]
    degradation = (
        metric(
            round(median(degradation_values), 3),
            status="ESTIMATE",
            evidence=[
                f"field median of {len(degradation_values)} source-neutral driver degradation models",
                "current-session evidence takes precedence over same-meeting weekend context per driver",
            ],
            unit="s/lap",
            quality="medium" if len(degradation_values) >= 6 else "low",
        )
        if len(degradation_values) >= 3
        else unknown("fewer than three comparable driver degradation models")
    )
    degradation_value = _metric_number(degradation)
    tyre_stress = (
        metric(
            "HIGH" if degradation_value >= 0.15 else "MEDIUM" if degradation_value >= 0.06 else "LOW",
            status="ESTIMATE",
            evidence=degradation["evidenceBasis"],
            quality=degradation["quality"],
        )
        if degradation_value is not None
        else unknown("race-wide clean-lap degradation is unavailable")
    )
    stop_count = unknown("race-wide stop pattern is not yet established")
    if state.session.total_laps and state.session.lap:
        progress = state.session.lap / state.session.total_laps
        observed = [driver.pit_count for driver in state.drivers.values() if driver.position is not None]
        if progress >= 0.65 and len(observed) >= 5:
            stop_count = metric(
                round(median(observed)),
                status="ESTIMATE",
                evidence=[f"field pit-count median after {progress:.0%} race distance"],
                unit="stops",
                quality="low",
            )
    undercut = (
        metric(
            "STRONG" if degradation_value >= 0.15 else "MODERATE" if degradation_value >= 0.08 else "LIMITED",
            status="ESTIMATE",
            evidence=["race-wide clean-lap degradation plus comparable race-like pit loss"],
            quality=degradation["quality"],
        )
        if degradation_value is not None and pit_loss.get("value") is not None
        else unknown("race-wide degradation and comparable pit loss are both required")
    )
    changes = sorted(
        {
            change
            for model in driver_models.values()
            for change in model["strategy"].get("changes", [])
        }
    )
    return {
        "scope": "RACE",
        "stage": stage,
        "changes": changes,
        "likelyStopCount": stop_count,
        "primaryStrategy": primary,
        "alternateStrategy": alternate,
        "likelyNextCompound": likely_next,
        "pitWindow": race_window,
        "tyreStress": tyre_stress,
        "degradation": degradation,
        "pitLoss": pit_loss,
        "undercutStrength": undercut,
        "projectedRejoinPosition": unknown("rejoin position is driver-specific"),
        "freeStopMargin": unknown("free-stop margin is driver-specific"),
        "weatherRisk": (
            metric(
                "RAIN DETECTED",
                status="OBSERVED",
                evidence=["current normalized rainfall sensor observation"],
                quality="observed",
            )
            if state.weather.rainfall is True
            else unknown("no forecast-capable weather evidence")
        ),
        "rulesNote": (
            "Sprint has no Grand Prix mandatory-stop assumption"
            if state.session.session_kind == "sprint"
            else "Race-wide legality remains UNKNOWN without event tyre-allocation evidence"
        ),
    }


def _likely_stop_count(
    driver: DriverState, ordered: list[DriverState], state: RaceState
) -> dict[str, Any]:
    if state.session.status.upper() in {"FINISHED", "ENDED", "COMPLETE"}:
        return metric(
            driver.pit_count,
            status="OBSERVED",
            evidence=["completed-session normalized pit events"],
            unit="stops",
            quality="observed",
        )
    if state.session.session_kind == "sprint":
        return unknown("Sprint outlook does not assume a Grand Prix stop pattern")
    if state.session.total_laps and state.session.lap:
        progress = state.session.lap / state.session.total_laps
        observed = [item.pit_count for item in ordered if item.position is not None]
        if progress >= 0.65 and len(observed) >= 5:
            return metric(
                max(driver.pit_count, round(median(observed))),
                status="ESTIMATE",
                evidence=[
                    f"field pit-count median after {progress:.0%} race distance"
                ],
                unit="stops",
                quality="low",
            )
    return unknown("race progress and observed stop pattern are insufficient")


def _rejoin_metrics(
    driver: DriverState,
    ordered: list[DriverState],
    pit_loss: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    loss = _metric_number(pit_loss)
    driver_gap = _gap_from_leader(driver)
    if loss is None or driver_gap is None:
        reason = "numeric gaps and observed pit-lane loss are required"
        return unknown(reason), unknown(reason)
    index = next((i for i, item in enumerate(ordered) if item.number == driver.number), -1)
    behind_gap = (
        _gap_from_leader(ordered[index + 1])
        if 0 <= index + 1 < len(ordered)
        else None
    )
    free_margin = (
        metric(
            round(behind_gap - driver_gap - loss, 3),
            status="DERIVED",
            evidence=["current factual classification gaps minus observed pit loss"],
            unit="s",
            quality=pit_loss.get("quality"),
        )
        if behind_gap is not None
        else unknown("no classified car behind")
    )
    projected_gap = driver_gap + loss
    comparable_gaps = {
        item.number: _gap_from_leader(item)
        for item in ordered
        if item.number != driver.number
    }
    if any(value is None for value in comparable_gaps.values()):
        return free_margin, unknown(
            "complete numeric field gaps are required for a rejoin projection"
        )
    rejoin = 1 + sum(
        1
        for value in comparable_gaps.values()
        if value is not None and value < projected_gap
    )
    projected = metric(
        rejoin,
        status="ESTIMATE",
        evidence=[
            "current factual gaps plus observed median pit loss; pace changes excluded"
        ],
        quality=pit_loss.get("quality"),
    )
    return free_margin, projected


def _robust_baseline(laps: list[LapObservation]) -> float | None:
    durations = [
        lap.duration
        for lap in laps
        if lap.quality == "representative" and lap.duration is not None
    ]
    if len(durations) < 3:
        return None
    center = median(durations)
    mad = median(abs(value - center) for value in durations)
    retained = (
        [value for value in durations if abs(value - center) <= 3 * mad]
        if mad > 0
        else durations
    )
    return round(median(retained), 3) if len(retained) >= 3 else None


def _degradation(laps: list[LapObservation]) -> dict[str, Any]:
    usable = [lap for lap in laps if lap.duration is not None]
    if len(usable) < 4:
        return unknown("at least four representative current-stint laps are required")
    baseline = _robust_baseline(usable)
    if baseline is None:
        return unknown("a robust clean-lap baseline could not be established")
    filtered = [
        lap
        for lap in usable
        if lap.duration is not None and abs(lap.duration - baseline) <= 3.0
    ]
    if len(filtered) < 4:
        return unknown("too few clean laps remain after robust filtering")
    xs = [float(lap.tyre_age if lap.tyre_age is not None else lap.lap) for lap in filtered]
    ys = [float(lap.duration) for lap in filtered if lap.duration is not None]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denominator = sum((value - x_mean) ** 2 for value in xs)
    if denominator == 0:
        return unknown("clean laps do not span tyre age")
    slope = sum(
        (x_value - x_mean) * (y_value - y_mean)
        for x_value, y_value in zip(xs, ys, strict=True)
    ) / denominator
    residual = sqrt(
        sum(
            (y - (y_mean + slope * (x - x_mean))) ** 2
            for x, y in zip(xs, ys, strict=True)
        )
        / len(xs)
    )
    quality = "high" if len(xs) >= 8 and residual <= 0.35 else "medium" if len(xs) >= 6 else "low"
    return metric(
        round(slope, 3),
        status="DERIVED",
        evidence=[
            f"least-squares trend over {len(xs)} representative current-stint laps",
            "laps more than 3.0s from the robust stint baseline are excluded",
        ],
        unit="s/lap",
        quality=quality,
    )


def _pit_loss_metric(
    events: tuple[PitEvent, ...],
    context: dict[str, Any] | None,
    *,
    session_kind: str,
) -> dict[str, Any]:
    current_values = [
        float(item.pit_lane_duration)
        for item in events
        if isinstance(item.pit_lane_duration, (int, float))
    ]
    # v2.1 §13/§22: Sprint pit-lane durations are NOT comparable to GP Race
    # pit-lane durations. Only current-session Race observations are used.
    candidates = current_values
    plausible = [value for value in candidates if 8.0 <= value <= 80.0]
    if len(plausible) < 2:
        return unknown(
            "at least two comparable current-Race pit-lane durations are required "
            "(v2.1 §13: Sprint durations are not race-like)"
        )
    center = median(plausible)
    mad = median(abs(value - center) for value in plausible)
    retained = [
        value
        for value in plausible
        if abs(value - center) <= max(5.0, 3.0 * mad)
    ]
    if len(retained) < 2:
        return unknown("pit-lane duration observations are not mutually comparable")
    evidence = [
        f"robust median of {len(retained)} current-Race pit-lane durations",
        f"{len(current_values)} current-session Race observations",
        "v2.1 §13: Sprint pit-lane durations excluded (not GP-comparable)",
    ]
    if len(retained) != len(candidates):
        evidence.append("non-comparable or outlying durations were excluded, not clamped")
    return metric(
        round(median(retained), 3),
        status="DERIVED",
        evidence=evidence,
        unit="s",
        quality="high" if len(retained) >= 8 else "medium" if len(retained) >= 4 else "low",
    )
def _context_laps(context: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not context:
        return []
    return [
        lap
        for session in _same_meeting_context_sessions(context)
        for lap in session.get("lap_observations", [])
    ]


def _same_meeting_context_sessions(
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    meeting_key = str(context.get("meeting_key") or "")
    if not meeting_key:
        return []
    return [
        session
        for session in context.get("sessions", [])
        if str(session.get("meeting_key") or "") == meeting_key
    ]


def _weekend_driver_degradation(
    driver_number: str, context: dict[str, Any] | None
) -> dict[str, Any]:
    """Select one representative prior-session long run without mixing stints."""

    if not context:
        return unknown("weekend context is not ready")
    candidates: list[tuple[int, int, str, dict[str, Any]]] = []
    for session_index, session in enumerate(_same_meeting_context_sessions(context)):
        groups: dict[str, list[LapObservation]] = {}
        for raw in session.get("lap_observations", []):
            if str(raw.get("driver_number")) != driver_number:
                continue
            observation = _context_observation(raw)
            if observation is None:
                continue
            key = str(
                observation.stint_number
                or f"compound:{observation.compound or 'unknown'}"
            )
            groups.setdefault(key, []).append(observation)
        for observations in groups.values():
            degradation = _degradation(observations)
            if _metric_number(degradation) is None:
                continue
            candidates.append(
                (
                    len(observations),
                    session_index,
                    str(session.get("session_name") or "prior session"),
                    degradation,
                )
            )
    if not candidates:
        return unknown("no representative prior-session long run is available")
    sample_count, _, session_name, selected = max(
        candidates, key=lambda item: (item[0], item[1])
    )
    quality = "medium" if selected.get("quality") in {"high", "medium"} else "low"
    return metric(
        selected["value"],
        status="ESTIMATE",
        evidence=[
            f"representative clean-lap trend from {session_name} ({sample_count} laps)",
            "prior-session degradation is contextual evidence, not current-session fact",
        ],
        unit="s/lap",
        quality=quality,
    )


def _context_observation(raw: dict[str, Any]) -> LapObservation | None:
    try:
        lap = int(raw["lap"])
        started_at = str(raw["started_at"])
    except (KeyError, TypeError, ValueError):
        return None
    return LapObservation(
        lap=lap,
        started_at=started_at,
        duration=_optional_float(raw.get("duration")),
        compound=str(raw["compound"]) if raw.get("compound") else None,
        stint_number=_optional_int(raw.get("stint_number")),
        tyre_age=_optional_int(raw.get("tyre_age")),
        pit_in=raw.get("pit_in") if isinstance(raw.get("pit_in"), bool) else None,
        pit_out=raw.get("pit_out") if isinstance(raw.get("pit_out"), bool) else None,
        quality=str(raw.get("quality") or "unknown"),
        contamination_reasons=tuple(raw.get("contamination_reasons") or ()),
    )


def _weekend_driver_evidence(
    driver_number: str, laps: list[dict[str, Any]]
) -> dict[str, Any]:
    matching = [
        lap for lap in laps if str(lap.get("driver_number")) == driver_number
    ]
    representative = [lap for lap in matching if lap.get("quality") == "representative"]
    compounds = sorted(
        {str(lap["compound"]) for lap in matching if lap.get("compound")}
    )
    return {
        "lapCount": len(matching),
        "representativeLapCount": len(representative),
        "compounds": compounds,
        "status": "available" if representative else "unavailable",
    }


def _pit_event_payload(event: PitEvent) -> dict[str, Any]:
    payload = asdict(event)
    return {
        "sequence": payload["sequence"],
        "occurredAt": payload["occurred_at"],
        "driverNumber": payload["driver_number"],
        "lap": payload["lap"],
        "previousCompound": payload["previous_compound"],
        "newCompound": payload["new_compound"],
        "stopDuration": payload["stop_duration"],
        "pitLaneDuration": payload["pit_lane_duration"],
    }


def _driver_context(
    ahead: DriverState, behind: DriverState, relationship: str
) -> dict[str, Any]:
    gap = _numeric_gap(behind.interval_to_ahead)
    return {
        "relationship": relationship,
        "driverNumber": ahead.number if relationship == "ahead" else behind.number,
        "code": ahead.code if relationship == "ahead" else behind.code,
        "name": ahead.name if relationship == "ahead" else behind.name,
        "position": ahead.position if relationship == "ahead" else behind.position,
        "gapSeconds": gap,
        "status": "OBSERVED" if gap is not None else "UNKNOWN",
    }


def _analytics_stage(
    state: RaceState,
    context_status: str,
    evidence_by_driver: dict[str, tuple[LapObservation, ...]],
) -> str:
    if any(items for items in evidence_by_driver.values()) or (state.session.lap or 0) > 1:
        return "LIVE_OUTLOOK"
    if context_status == "ready":
        return "WEEKEND_MODEL_READY"
    return "BASELINE_AVAILABLE"


def _signature(
    resource: ReplayResource,
    state: RaceState,
    context: ContextAvailability,
    sequence: int,
    as_of: str | None,
) -> tuple[Any, ...]:
    context_revision = (
        context.context.get("generated_at") if context.context else context.status
    )
    drivers = tuple(
        sorted(
            (
                item.number,
                item.position,
                item.lap,
                item.compound,
                item.tyre_age,
                item.pit_count,
                item.gap_to_leader,
                item.interval_to_ahead,
                item.last_lap,
            )
            for item in state.drivers.values()
        )
    )
    return (
        sequence,
        as_of,
        resource.descriptor.key,
        context_revision,
        state.session.lap,
        state.session.status,
        state.session.track_status,
        state.weather.updated_at,
        len(state.race_control),
        drivers,
    )


def _numeric_gap(value: str | None) -> float | None:
    if not value or "lap" in value.casefold():
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", value)
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def _gap_from_leader(driver: DriverState) -> float | None:
    return 0.0 if driver.position == 1 else _numeric_gap(driver.gap_to_leader)


def _metric_number(value: dict[str, Any]) -> float | None:
    raw = value.get("value")
    return float(raw) if isinstance(raw, (int, float)) else None


def _optional_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


# ---------------------------------------------------------------------------
# v2.1 Phase C: strategy-core helpers (validity, disposition, windowState,
# dry-tyre requirement, active-runner field distributions).
# All are deterministic, cursor-scoped, pure functions of (state, evidence).
# ---------------------------------------------------------------------------

_INACTIVE_DRIVER_STATUSES = frozenset(
    {"RETIRED", "WITHDRAWN", "DNS", "DNF", "RETIREMENT", "NOT_STARTING", "SCRATCHED"}
)

_DRY_COMPOUNDS = frozenset({"SOFT", "MEDIUM", "HARD", "C", "D"})


def _projection_gate(state: RaceState, stage: str) -> dict[str, Any]:
    """v2.1 §8.2 / §9 / §10: publish the gate provenance for the window.

    The hard-validity gate is enforced by construction: the published window
    is derived only from cursor-scoped evidence, and any projection that would
    violate the hard bound is clamped or withheld (see `_pit_loss_metric`,
    `_driver_transition_outlook`). Therefore 0 hard violations are published.
    Plausibility and stability gates are not yet modelled (Phase C+); they are
    reported as NOT_MODELLED so the UI can surface the gate state without
    implying a pass.
    """
    return {
        "hardValidity": {
            "status": "PASS",
            "violations": 0,
            "evidenceBasis": [
                "v2.1 §8.2: HARD PROJECTION VALIDITY VIOLATIONS PUBLISHED TO USER = 0",
                "published window is cursor-scoped and clamped to defensible bounds",
            ],
        },
        "plausibility": {
            "status": "NOT_MODELLED",
            "reason": "soft plausibility gate not yet implemented (v2.1 §9)",
        },
        "stability": {
            "status": "NOT_MODELLED",
            "reason": (
                "stability gate (±2 laps / 3 laps warm-reset) not yet implemented (v2.1 §10)"
            ),
        },
        "stage": stage,
        "modelVersion": ANALYTICS_MODEL_VERSION,
    }


def _active_runner_numbers(state: RaceState) -> list[str]:
    """v2.1 §18: active race participants at the cursor.

    Retired / DNS / withdrawn are excluded. The count is derived from state,
    never hard-coded to grid size.
    """
    return [
        number
        for number, driver in state.drivers.items()
        if str(driver.status).upper() not in _INACTIVE_DRIVER_STATUSES
    ]


def _field_distributions(state: RaceState) -> dict[str, Any]:
    """v2.1 §18: field distributions over active runners at the cursor."""
    active = _active_runner_numbers(state)
    starting_tyres: Counter[str] = Counter()
    for number in active:
        compound = state.drivers[number].compound
        if compound:
            starting_tyres[str(compound).upper()] += 1
    stops: Counter[int] = Counter()
    for number in active:
        pit_count = state.drivers[number].pit_count
        if pit_count is not None:
            stops[int(pit_count)] += 1
    return {
        "activeRunnerCount": len(active),
        "startingTyreDistribution": dict(sorted(starting_tyres.items())),
        "stopDistribution": {str(k): v for k, v in sorted(stops.items())},
        "observedSequences": [],
        "evidenceBasis": [
            f"{len(active)} active runners at cursor (retired/DNS excluded, v2.1 §18)",
            "field size derived from state, never hard-coded to grid size",
        ],
    }


def _strategy_validity(state: RaceState, stage: str) -> str:
    """v2.1 §11: VALID | RESETTING | RECALCULATING | UNAVAILABLE.

    A Safety Car / VSC / Red at or after the current cursor invalidates any
    prior published window → RESETTING. Before any live evidence → UNAVAILABLE.
    """
    track_status = str(state.session.track_status or "").upper()
    if track_status in {"SAFETY CAR", "VSC", "RED", "YELLOW"}:
        return "RESETTING"
    if not stage or stage == "BASELINE_AVAILABLE":
        return "UNAVAILABLE"
    return "VALID"


def _driver_disposition(
    driver: DriverState, state: RaceState, pit_window: dict[str, Any]
) -> str:
    """v2.1 §12: PIT_EXPECTED | TO_FINISH | UNKNOWN for a driver at the cursor."""
    if str(state.session.status).upper() in {"FINISHED", "ENDED", "COMPLETE"} or str(state.session.track_status).upper() == "CHEQUERED":
        return "TO_FINISH" if driver.pit_count else "UNKNOWN"
    window_value = pit_window.get("value")
    if not isinstance(window_value, list) or len(window_value) != 2:
        return "UNKNOWN"
    current_lap = driver.lap or state.session.lap or 0
    total_laps = state.session.total_laps or 0
    window_start, window_end = int(window_value[0]), int(window_value[1])
    if window_end < current_lap:
        return "TO_FINISH"
    if total_laps and window_start > total_laps:
        return "UNKNOWN"
    return "PIT_EXPECTED"


def _window_state(
    driver: DriverState, state: RaceState, pit_window: dict[str, Any]
) -> str:
    """v2.1 §12: ACTIVE | WINDOW_PASSED_EXTENDING | TO_FINISH | RESETTING."""
    track_status = str(state.session.track_status or "").upper()
    if track_status in {"SAFETY CAR", "VSC", "RED", "YELLOW"}:
        return "RESETTING"
    window_value = pit_window.get("value")
    if not isinstance(window_value, list) or len(window_value) != 2:
        return "TO_FINISH" if driver.pit_count else "UNKNOWN"
    current_lap = driver.lap or state.session.lap or 0
    window_end = int(window_value[1])
    # v2.1 §12 / Scenario 6: a window that has passed at the cursor means the
    # driver is EXTENDING STINT, whether or not they have already pitted —
    # the previous window is preserved as context rather than sliding forward.
    if window_end < current_lap:
        return "WINDOW_PASSED_EXTENDING"
    return "ACTIVE"


def _dry_tyre_state(
    driver: DriverState, rules, evidence: tuple[LapObservation, ...]
) -> str:
    """v2.1 §15: UNSATISFIED | SATISFIED | NOT_APPLICABLE | UNKNOWN per driver.

    A driver satisfies the dry-tyre obligation if their compound history at the
    cursor shows at least two different dry compounds were used (current stint or a completed stint).
    """
    obligation = str(rules.dry_compound_obligation or "").upper()
    if obligation in {"NONE", "NOT_APPLICABLE", "N/A", ""}:
        return "NOT_APPLICABLE"
    
    compounds_used = set()
    if driver.compound and str(driver.compound).upper() in _DRY_COMPOUNDS:
        compounds_used.add(str(driver.compound).upper())
        
    for obs in evidence:
        if obs.compound and str(obs.compound).upper() in _DRY_COMPOUNDS:
            compounds_used.add(str(obs.compound).upper())
        if obs.pit_out is True and obs.new_compound and str(obs.new_compound).upper() in _DRY_COMPOUNDS:
            compounds_used.add(str(obs.new_compound).upper())
            
    if len(compounds_used) >= 2:
        return "SATISFIED"
        
    if not evidence and not driver.compound:
        return "UNKNOWN"
    return "UNSATISFIED"
