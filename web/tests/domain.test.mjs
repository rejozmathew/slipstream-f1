import assert from "node:assert/strict";
import test from "node:test";

import { isCriticalTrackStatus, nextAuthoredState } from "../domain/tvMode.mjs";
import {
  battleFactorPresentation,
  battleGapPresentation,
  gapChartModel,
  isTrackMapActive,
  lapDeficitGap,
  paceChartAvailability,
  trackCoverage,
} from "../domain/correctness.mjs";
import {
  reconciledPendingPosition,
  replayDisplayPosition,
  replayKeyboardPosition,
  sessionClockLabel,
} from "../domain/replayControls.mjs";
import { preferredWeekendSession } from "../domain/sessionSelection.mjs";

// v2.1 §20 / invariant 6: Battle hysteresis is SERVER-owned (AnalyticsService,
// session-scoped + cursor-keyed, pinned in tests/test_strategy_v21_battle.py).
// The prior client `advanceBattleRecommendation` module and its tests are
// removed — the client now renders the server's stabilized recommendation.

test("TV rotation follows the authored preference order", () => {
  const authored = ["tower", "battle", "driver"];

  assert.equal(nextAuthoredState(authored, "tower"), "battle");
  assert.equal(nextAuthoredState(authored, "driver"), "tower");
  assert.equal(nextAuthoredState(authored, "strategy"), "battle");
});

test("TV alerts distinguish critical track states from normal running", () => {
  assert.equal(isCriticalTrackStatus("GREEN"), false);
  assert.equal(isCriticalTrackStatus("DOUBLE YELLOW"), true);
  assert.equal(isCriticalTrackStatus("VSC ENDING"), true);
  assert.equal(isCriticalTrackStatus("RED FLAG"), true);
});

test("pace chart is unavailable without a representative signed delta", () => {
  assert.deepEqual(
    paceChartAvailability([
      { quality: "contaminated", delta: null },
      { quality: "unknown", delta: 0.2 },
    ]),
    { available: false, representativeCount: 0, excludedCount: 2 },
  );
  assert.equal(
    paceChartAvailability([{ quality: "representative", delta: -0.1 }]).available,
    true,
  );
});

test("gap chart axes contain every plotted source value", () => {
  const model = gapChartModel([
    { gapSeconds: 1.2 },
    { gapSeconds: 3.4 },
    { gapSeconds: 2.1 },
  ]);
  assert.ok(model);
  assert.equal(model.min, 1.2);
  assert.equal(model.max, 3.4);
  assert.ok(model.points.every((point) => point.value >= model.min && point.value <= model.max));
  assert.ok(model.points.every((point) => point.y >= 7 && point.y <= 34));
});

test("track coverage accounts for missing cars without inventing coordinates", () => {
  const coverage = trackCoverage([
    { number: "1", code: "NOR", position: 1, status: "RUNNING", source_condition: "RUNNING", track_position: 0.4 },
    { number: "2", code: "VER", position: 2, status: "RUNNING", source_condition: "RUNNING", track_position: null },
    { number: "3", code: "PIA", position: null, status: "RUNNING", source_condition: "RUNNING", track_position: null },
  ], "timing_estimate");
  assert.deepEqual(coverage, {
    eligible: 3,
    positioned: 1,
    unpositioned: 2,
    unpositionedLabels: ["VER", "PIA"],
    inactiveLabels: [],
  });
});

test("track coverage is over active cars and reports factual out states", () => {
  const active = { number: "1", code: "NOR", position: 1, status: "RUNNING", source_condition: "RUNNING", track_position: 0.4 };
  const stopped = { number: "2", code: "VER", position: 2, status: "STOPPED", source_condition: "STOPPED", track_position: 0.5 };
  const dnf = { number: "3", code: "PIA", position: 3, status: "DNF", classification: "DNF", track_position: 0.6 };
  assert.equal(isTrackMapActive(active), true);
  assert.equal(isTrackMapActive(stopped), false);
  const coverage = trackCoverage([active, stopped, dnf], "timing_estimate");
  assert.deepEqual(coverage, {
    eligible: 1,
    positioned: 1,
    unpositioned: 0,
    unpositionedLabels: [],
    inactiveLabels: ["VER · STOPPED", "PIA · DNF"],
  });
});

test("transient in-pit cars are omitted from markers without entering OUT / STOPPED", () => {
  const inPit = { number: "1", code: "NOR", status: "IN_PIT", source_condition: "IN_PIT", activity: "IN_PIT", track_position: 0.4 };
  const stopped = { number: "2", code: "VER", status: "STOPPED", source_condition: "STOPPED", track_position: null };
  const coverage = trackCoverage([inPit, stopped], "timing_estimate");

  assert.equal(isTrackMapActive(inPit), false);
  assert.deepEqual(coverage.inactiveLabels, ["VER · STOPPED"]);
  assert.equal(coverage.inactiveLabels.some((label) => label.includes("IN PIT")), false);
});

test("lap deficits are shown only when a usable seconds gap is absent", () => {
  const leader = { number: "1", position: 1, lap: 45 };
  assert.equal(lapDeficitGap({ position: 7, lap: 44, gap_to_leader: null, availability: {} }, leader), "+1 LAP");
  assert.equal(lapDeficitGap({ position: 12, lap: 42, gap_to_leader: null, availability: {} }, leader), "+3 LAPS");
  assert.equal(lapDeficitGap({ position: 2, lap: 45, gap_to_leader: "+1.250", availability: { gap_to_leader: "available" } }, leader), null);
});

test("battle contributions remain distinct from raw factor values", () => {
  assert.deepEqual(
    battleFactorPresentation({ name: "current_gap", value: 0.31, weight: 68.45 }),
    {
      contributionLabel: "CURRENT GAP CONTRIBUTION",
      contribution: "+68.5 PTS",
      raw: "RAW 0.31 s",
    },
  );
});

test("interval feed is never claimed as same-snapshot gap arithmetic", () => {
  const presentation = battleGapPresentation({ gapBasis: "interval_to_ahead" });
  assert.equal(presentation.sameSnapshotArithmetic, false);
  assert.match(presentation.label, /SOURCE FEED/);
  assert.match(presentation.note, /NOT SAME-SNAPSHOT ARITHMETIC/);
});

test("weekend selection preserves the current session then follows product priority", () => {
  const sessions = [
    { sessionKey: "p1", sessionKind: "practice_1", dateStart: "2026-01-01T10:00:00Z" },
    { sessionKey: "q", sessionKind: "qualifying", dateStart: "2026-01-02T10:00:00Z" },
    { sessionKey: "s", sessionKind: "sprint", dateStart: "2026-01-02T12:00:00Z" },
    { sessionKey: "r", sessionKind: "race", dateStart: "2026-01-03T10:00:00Z" },
  ];

  assert.equal(preferredWeekendSession(sessions, "q").sessionKey, "q");
  assert.equal(preferredWeekendSession(sessions, "other").sessionKey, "r");
  assert.equal(preferredWeekendSession(sessions.filter((item) => item.sessionKind !== "race"), null).sessionKey, "s");
});

test("local scrub preview owns the thumb until the committed server position arrives", () => {
  assert.equal(replayDisplayPosition(10, 45, null), 45);
  assert.equal(replayDisplayPosition(10, null, 45), 45);
  assert.equal(reconciledPendingPosition(10, 45), 45);
  assert.equal(reconciledPendingPosition(45, 45), null);
  assert.equal(sessionClockLabel("2026-08-23T13:00:00Z", 3600, "02:00:00"), "16:00:00");
  assert.equal(replayKeyboardPosition("End", 0, 8928), 8928);
  assert.equal(replayKeyboardPosition("Home", 4200, 8928), 0);
  assert.equal(replayKeyboardPosition("PageUp", 0, 8928), 893);
  assert.equal(replayKeyboardPosition("ArrowLeft", 0, 8928), 0);
  assert.equal(replayKeyboardPosition("Enter", 10, 8928), null);
});
