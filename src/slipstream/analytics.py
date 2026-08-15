"""Deterministic, source-neutral replay analytics with explicit provenance."""

from __future__ import annotations

import re
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from math import sqrt
from statistics import median
from typing import Any

from .evidence import LapObservation, PitEvent
from .library import ReplayResource
from .state import DriverState, RaceState
from .strategy_rules import strategy_rule_profile
from .weekend import ContextAvailability

ANALYTICS_SCHEMA_VERSION = 1
ANALYTICS_MODEL_VERSION = "race-intelligence-v1"


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


class AnalyticsService:
    """Cache calculations by meaningful factual/context revisions."""

    def __init__(self) -> None:
        self._cache: dict[tuple[Any, ...], dict[str, Any]] = {}

    def snapshot(
        self,
        resource: ReplayResource,
        state: RaceState,
        *,
        sequence: int,
        as_of: str | None,
        context: ContextAvailability,
    ) -> dict[str, Any]:
        signature = _signature(resource, state, context)
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
        return response


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
    pit_loss = _pit_loss_metric(pit_events, context_payload)
    stage = _analytics_stage(state, context.status, evidence_by_driver)
    ordered = sorted(
        state.drivers.values(), key=lambda item: item.position or 999
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
                pit_events,
                pit_loss,
                pace,
                weekend_degradation,
                state,
                stage,
            ),
            "weekendEvidence": _weekend_driver_evidence(
                driver.number, context_laps
            ),
        }
    battle = battle_recommendation(ordered, driver_models)
    rules = strategy_rule_profile(
        resource.descriptor.year, resource.descriptor.session_kind
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
        "sportingRules": {
            "profileVersion": rules.profile_version,
            "mandatoryPitStops": rules.mandatory_pit_stops,
            "dryCompoundObligation": rules.dry_compound_obligation,
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
    }


def battle_recommendation(
    ordered: list[DriverState], driver_models: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for index in range(1, len(ordered)):
        ahead = ordered[index - 1]
        behind = ordered[index]
        gap = _numeric_gap(behind.interval_to_ahead)
        if gap is None:
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
    return {
        "recommended": candidates[0] if candidates else None,
        "candidates": candidates,
        "hysteresis": {"minimumHoldSeconds": 20, "switchMargin": 8},
        "modelVersion": ANALYTICS_MODEL_VERSION,
    }


def _driver_strategy(
    driver: DriverState,
    ordered: list[DriverState],
    laps: tuple[LapObservation, ...],
    pit_events: tuple[PitEvent, ...],
    pit_loss: dict[str, Any],
    pace: dict[str, Any],
    weekend_degradation: dict[str, Any],
    state: RaceState,
    stage: str,
) -> dict[str, Any]:
    transitions = [
        item
        for item in pit_events
        if item.previous_compound == driver.compound
        and item.new_compound
        and item.new_compound != item.previous_compound
    ]
    counts = Counter(item.new_compound for item in transitions if item.new_compound)
    common = counts.most_common()
    next_compound = (
        metric(
            common[0][0],
            status="ESTIMATE",
            evidence=[
                f"{common[0][1]} observed same-compound transitions in this session"
            ],
            quality="medium" if common[0][1] >= 4 else "low",
        )
        if common and common[0][1] >= 2
        else unknown("fewer than two comparable observed compound transitions")
    )
    transition_laps = sorted(item.lap for item in transitions)
    pit_window = (
        metric(
            [
                transition_laps[len(transition_laps) // 4],
                transition_laps[(len(transition_laps) * 3) // 4],
            ],
            status="ESTIMATE",
            evidence=[
                f"central range of {len(transition_laps)} comparable pit laps"
            ],
            unit="lap",
            quality="medium" if len(transition_laps) >= 5 else "low",
        )
        if len(transition_laps) >= 3
        else unknown("insufficient comparable pit-lap evidence")
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
        if driver.compound and len(common) > 1 and common[1][1] >= 2
        else unknown("no supported alternate compound consensus")
    )
    free_stop, projected_rejoin = _rejoin_metrics(driver, ordered, pit_loss)
    undercut = (
        metric(
            "STRONG"
            if degradation_value >= 0.15
            else "MODERATE"
            if degradation_value >= 0.08
            else "LIMITED",
            status="ESTIMATE",
            evidence=[
                "clean-lap degradation; traffic and warm-up effects are not modelled"
            ],
            quality=degradation.get("quality"),
        )
        if degradation_value is not None and pit_loss.get("value") is not None
        else unknown("degradation and observed pit loss are both required")
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
        "stage": stage,
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
    events: tuple[PitEvent, ...], context: dict[str, Any] | None
) -> dict[str, Any]:
    values = [item.pit_lane_duration for item in events if item.pit_lane_duration]
    if context:
        values.extend(
            float(lap["pit_lane_duration"])
            for session in context.get("sessions", [])
            for lap in session.get("lap_observations", [])
            if isinstance(lap.get("pit_lane_duration"), (int, float))
        )
    if len(values) < 2:
        return unknown("at least two observed pit-lane durations are required")
    return metric(
        round(median(values), 3),
        status="DERIVED",
        evidence=[f"median of {len(values)} observed pit-lane durations"],
        unit="s",
        quality="high" if len(values) >= 8 else "medium" if len(values) >= 4 else "low",
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
