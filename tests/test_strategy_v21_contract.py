"""v2.1 strategy contract tests (Phase A: schema/contract level).

These tests pin the *contract surface* that Phases B–H implement: the snapshot
must always carry the new v2.1 fields (disposition, windowState,
strategyValidity, dryTyreRequirement, netPitLoss, projectionGate, active-runner
population, official/historical context blocks, battle hysteresis) so the API
shape is stable before behavior lands.

Behavioral semantics (values, gates, suppression) are Phase C+.
"""

import tempfile
from pathlib import Path

from test_intelligence import descriptor as _make_descriptor

from slipstream.analytics import ANALYTICS_MODEL_VERSION, build_analytics_snapshot
from slipstream.context_types import (
    DISPOSITION_STATES,
    DRY_TYRE_REQUIREMENT_STATES,
    HISTORICAL_COMPARABILITY_STATES,
    NET_PIT_LOSS_BLOCKED_BY,
    STRATEGY_VALIDITY_STATES,
    WINDOW_STATES,
    HistoricalContext,
    OfficialPreRaceContext,
    absent_historical,
    absent_official_pre_race,
)
from slipstream.evidence import SessionEvidence
from slipstream.library import ReplayResource
from slipstream.state import DriverState, RaceState
from slipstream.weekend import ContextAvailability


def _snapshot(two: bool = False):
    with tempfile.TemporaryDirectory() as tmp:
        descriptor = _make_descriptor(Path(tmp), kind="Race")
        state = RaceState(
            drivers={
                "1": DriverState(number="1", position=1, compound="MEDIUM", status="RACING"),
                "2": DriverState(number="2", position=2, compound="HARD", status="RACING"),
                **({"3": DriverState(number="3", position=3, compound="SOFT", status="RACING")} if two else {}),
            }
        )
        resource = ReplayResource(
            descriptor=descriptor,
            events=(),
            final_state=state,
            evidence=SessionEvidence(),
            replay_available=False,
            is_live=False,
        )
        return build_analytics_snapshot(
            resource,
            state,
            sequence=1,
            as_of="2026-08-01T14:00:00+00:00",
            context=ContextAvailability(status="missing"),
        )


def test_snapshot_carries_v21_contract_surface() -> None:
    snap = _snapshot()
    assert snap["type"] == "analytics.snapshot"
    assert snap["schemaVersion"] == 1
    assert "v2.1" in ANALYTICS_MODEL_VERSION

    # Race-level v2.1 contract fields (Phase C fills in real values).
    assert "strategyValidity" in snap
    assert "netPitLoss" in snap
    assert "projectionGate" in snap

    # Dry-tyre requirement is a rule-derived per-driver state (v2.1 §15), not
    # a single static "MUST STOP" obligation. Phase A publishes the *rule profile*
    # so the UI can explain the state; per-driver values land in Phase C.
    assert "dryTyreRequirement" in snap["sportingRules"]
    assert "ruleProfile" in snap["sportingRules"]["dryTyreRequirement"]
    assert "perDriverState" in snap["sportingRules"]["dryTyreRequirement"]

    # Per-driver contract: Phase A declares the v2.1 fields (disposition,
    # windowState, strategyValidity, dryTyreRequirement) as *optional* on the
    # StrategyAnalytics type (protocol.ts) and in the enum vocabulary
    # (context_types.py). Their per-driver *runtime values* are Phase C
    # (_driver_strategy). Phase A only guarantees the strategy block still
    # carries the existing rule provenance.
    for driver in snap["drivers"].values():
        strat = driver["strategy"]
        assert strat["scope"] == "DRIVER"
        assert "rulesNote" in strat
        assert "stage" in strat


def test_net_pit_loss_is_explicitly_absent_and_blocks_dependents() -> None:
    snap = _snapshot()
    assert snap["netPitLoss"]["status"] in ("ABSENT", "NOT_IMPLEMENTED", "UNKNOWN")
    assert set(snap["netPitLoss"]["blocks"]) == {
        "freeStopMargin",
        "projectedRejoinPosition",
        "undercutQuantified",
    }
    assert set(NET_PIT_LOSS_BLOCKED_BY) == set(snap["netPitLoss"]["blocks"])


def test_official_pre_race_context_contract() -> None:
    ctx = OfficialPreRaceContext(
        source="PIRELLI",
        published_at="2026-08-01T12:00:00+00:00",
        retrieved_at="2026-08-01T13:00:00+00:00",
        expected_stop_count=1,
        primary_sequence="M-S",
        acquisition="MANUAL",
        target_session_key="30",
    )
    payload = ctx.to_payload()
    assert payload["source"] == "PIRELLI"
    assert payload["expectedStopCount"] == 1
    assert payload["targetSessionKey"] == "30"
    assert payload["acquisition"] == "MANUAL"
    absent = absent_official_pre_race()
    assert absent["status"] == "ABSENT"


def test_historical_context_contract() -> None:
    ctx = HistoricalContext(
        season=2025,
        circuit_id="circuit-x",
        comparability="LIMITED",
        stop_distribution={"1": 12, "2": 8},
        compound_sequences=("M-H", "S-M"),
        target_session_key="30",
    )
    assert ctx.comparability in HISTORICAL_COMPARABILITY_STATES
    payload = ctx.to_payload()
    assert payload["season"] == 2025
    assert payload["stopDistribution"] == {"1": 12, "2": 8}
    assert payload["targetSessionKey"] == "30"
    assert absent_historical()["status"] == "ABSENT"


def test_v21_enum_vocabulary_is_closed_and_stable() -> None:
    # These vocabularies are part of the wire contract; the frontend
    # (protocol.ts) mirrors them. Do not add/remove states without a model bump.
    assert DISPOSITION_STATES == ("PIT_EXPECTED", "TO_FINISH", "UNKNOWN")
    assert WINDOW_STATES == (
        "ACTIVE",
        "WINDOW_PASSED_EXTENDING",
        "TO_FINISH",
        "RESETTING",
    )
    assert STRATEGY_VALIDITY_STATES == (
        "VALID",
        "RESETTING",
        "RECALCULATING",
        "UNAVAILABLE",
    )
    assert DRY_TYRE_REQUIREMENT_STATES == (
        "UNSATISFIED",
        "SATISFIED",
        "NOT_APPLICABLE",
        "UNKNOWN",
    )


def test_battle_hysteresis_constants_remain_server_owned() -> None:
    snap = _snapshot(two=True)
    battle = snap["battle"]
    # Hysteresis is a server-side stability gate (invariant 11) — the client
    # renders it, it does not recompute it. Phase D moves the *state* server-side
    # but the constants are already part of the server contract.
    assert "hysteresis" in battle
    assert battle["hysteresis"]["minimumHoldSeconds"] > 0
    assert battle["hysteresis"]["switchMargin"] > 0
    assert "modelVersion" in battle


def test_active_runner_population_is_a_contract_field() -> None:
    snap = _snapshot()
    # §18: field distributions are over *active runners* at the cursor.
    # The contract must expose the population so consumers (and Phase C) can
    # exclude retired/DNS cars without re-deriving the predicate.
    assert "activeRunnerCount" in snap
    assert "startingTyreDistribution" in snap
    assert "stopDistribution" in snap
    assert "observedSequences" in snap
    # With 2 active drivers in the fixture:
    assert snap["activeRunnerCount"] == 2


def test_historical_and_official_blocks_present_even_when_absent() -> None:
    snap = _snapshot()
    # v2.1 §5.2 / §5.3: the contract surfaces are always present; they may be
    # ABSENT (Phase F populates) but the shape must be stable.
    assert "historical" in snap
    assert "officialPreRace" in snap
    assert snap["historical"]["status"] in ("PRESENT", "ABSENT")
    assert snap["officialPreRace"]["status"] in ("PRESENT", "ABSENT")
