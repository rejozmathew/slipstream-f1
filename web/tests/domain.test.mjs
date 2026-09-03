import assert from "node:assert/strict";
import test from "node:test";

import { shouldPollAnalytics } from "../domain/analyticsPolling.mjs";
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
import {
  actualStrategyText,
  driverPirelliReferenceRows,
  driverPirelliStopWindowsText,
  driverPirelliStrategiesText,
  driverStrategyRelationship,
  dryTyreRequirementText,
  NO_SPECIFIC_PIRELLI_STRATEGY,
  nominationSummary,
  optionDeltaText,
  optionOrderNote,
  prioritizedPirelliContextFacts,
} from "../domain/pirelliPresentation.mjs";

function pirelliBaseline(overrides = {}) {
  return {
    status: "PRESENT",
    options: [],
    compoundSelection: null,
    contextFacts: [],
    ...overrides,
  };
}

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

test("analytics polling stops when Pirelli reaches a stable state", () => {
  assert.equal(shouldPollAnalytics("replay", "11280", "ready", "FETCHING"), true);
  assert.equal(shouldPollAnalytics("replay", "11280", "preparing", "ABSENT"), true);
  for (const status of ["PRESENT", "RETRYING", "ABSENT"]) {
    assert.equal(shouldPollAnalytics("replay", "11280", "ready", status), false);
  }
  assert.equal(shouldPollAnalytics("live", "11280", "ready", "FETCHING"), false);
});

test("Australia and Canada context-only publications stay present without inventing strategies", () => {
  const australia = pirelliBaseline({
    compoundSelection: { hard: "C3", medium: "C4", soft: "C5" },
    contextFacts: [{ category: "COMPOUND_OUTLOOK", statement: "The softest three compounds are nominated." }],
  });
  const canada = pirelliBaseline({
    compoundSelection: { hard: "C3", medium: "C4", soft: "C5" },
    contextFacts: [{ category: "STRATEGY_OUTLOOK", statement: "A one-stop strategy could again be preferred." }],
  });

  assert.equal(nominationSummary(australia.compoundSelection), "C3 HARD · C4 MEDIUM · C5 SOFT");
  assert.equal(driverStrategyRelationship(australia), NO_SPECIFIC_PIRELLI_STRATEGY);
  assert.equal(driverPirelliStrategiesText(australia), NO_SPECIFIC_PIRELLI_STRATEGY);
  assert.equal(driverStrategyRelationship(canada), NO_SPECIFIC_PIRELLI_STRATEGY);
  assert.equal(prioritizedPirelliContextFacts(canada.contextFacts, 1)[0].category, "STRATEGY_OUTLOOK");
});

test("Miami driver presentation resolves actual strategy and aligned stop timing", () => {
  const miami = pirelliBaseline({ options: [{ id: "option-1", rank: "FASTEST_PUBLISHED", order: "ORDERED", stopCount: 1, compounds: ["MEDIUM", "HARD"], pitWindows: [{ startLap: 22, endLap: 28 }] }] });
  const driver = { relation: "MATCHING_ONE", compatibleOptionIds: ["option-1"], observedCompounds: ["MEDIUM", "HARD"], actualStrategy: { compounds: ["MEDIUM", "HARD"], stopLaps: [24], completedStops: 1, observedStops: 1, evidenceComplete: true }, pirelliAssessment: "ALIGNED", pirelliSummary: "Actual tyre strategy and stop timing align with a published Pirelli strategy.", pirelliReferences: [{ optionId: "option-1", status: "ALIGNED", stopComparisons: [{ stopIndex: 0, actualLap: 24, publishedStartLap: 22, publishedEndLap: 28, status: "INSIDE" }] }], windows: [] };
  const rows = driverPirelliReferenceRows(miami, driver);

  assert.equal(actualStrategyText(driver), "M → H");
  assert.equal(driverPirelliStrategiesText(miami, driver), "M → H");
  assert.equal(driverPirelliStopWindowsText(miami, driver), "Actual L24 · Pirelli L22–28");
  assert.match(driverStrategyRelationship(miami, driver), /strategy and stop timing align/);
  assert.equal(rows[0].windows[0].state, "ALIGNED");
  assert.doesNotMatch(`${driverPirelliStrategiesText(miami, driver)} ${driverPirelliStopWindowsText(miami, driver)}`, /option-1|MATCHING_ONE|COMPLETED/);
});

test("Dutch presentation distinguishes no-stop applicability and different timing", () => {
  const dutch = pirelliBaseline({ options: [
    { id: "mh", rank: "FASTEST_PUBLISHED", order: "ORDERED", stopCount: 1, compounds: ["MEDIUM", "HARD"], pitWindows: [{ startLap: 27, endLap: 33 }] },
    { id: "sh", rank: "ALTERNATIVE", order: "ORDERED", stopCount: 1, compounds: ["SOFT", "HARD"], pitWindows: [{ startLap: 26, endLap: 32 }], publishedDeltaSeconds: 1.0 },
  ] });
  const noStop = { actualStrategy: { compounds: ["MEDIUM"], stopLaps: [], completedStops: 0, observedStops: 0, evidenceComplete: true }, pirelliAssessment: "STILL_APPLICABLE", pirelliSummary: "A published Pirelli tyre strategy is still applicable.", pirelliReferences: [{ optionId: "mh", status: "STILL_APPLICABLE", stopComparisons: [{ stopIndex: 0, actualLap: null, publishedStartLap: 27, publishedEndLap: 33, status: "NOT_OCCURRED" }] }, { optionId: "sh", status: "NO_MATCH", stopComparisons: [{ stopIndex: 0, actualLap: null, publishedStartLap: 26, publishedEndLap: 32, status: "NOT_OCCURRED" }] }], compatibleOptionIds: ["mh"], observedCompounds: ["MEDIUM"], windows: [] };
  const earlyStop = { ...noStop, actualStrategy: { compounds: ["MEDIUM", "HARD"], stopLaps: [2], completedStops: 1, observedStops: 1, evidenceComplete: true }, pirelliAssessment: "SAME_COMPOUNDS_DIFFERENT_TIMING", pirelliSummary: "Actual compounds match a published Pirelli strategy, but the stop timing differs.", pirelliReferences: [{ optionId: "mh", status: "SAME_COMPOUNDS_DIFFERENT_TIMING", stopComparisons: [{ stopIndex: 0, actualLap: 2, publishedStartLap: 27, publishedEndLap: 33, status: "OUTSIDE" }] }, { optionId: "sh", status: "NO_MATCH", stopComparisons: [] }] };
  assert.equal(actualStrategyText(noStop), "M");
  assert.equal(driverPirelliStrategiesText(dutch, noStop), "M → H");
  assert.equal(driverStrategyRelationship(dutch, noStop), "A published Pirelli tyre strategy is still applicable.");
  assert.equal(driverPirelliStopWindowsText(dutch, earlyStop), "Actual L2 · Pirelli L27–33");
  assert.match(driverStrategyRelationship(dutch, earlyStop), /stop timing differs/);
  assert.equal(optionDeltaText(dutch.options[1]), "Published delta · +1.0s");
  assert.equal(optionOrderNote({ order: "ANY_ORDER", compounds: ["MEDIUM", "HARD"] }), "Compounds may be used in either order.");
});

test("a non-matching driver gets neutral wording instead of an internal relation label", () => {
  const baseline = pirelliBaseline({ options: [{ id: "mh", rank: "FASTEST_PUBLISHED", order: "ORDERED", stopCount: 1, compounds: ["MEDIUM", "HARD"], pitWindows: [{ startLap: 22, endLap: 28 }] }] });
  const driver = { relation: "DIVERGED", compatibleOptionIds: [], observedCompounds: ["SOFT", "MEDIUM"], windows: [] };
  assert.equal(driverStrategyRelationship(baseline, driver), "No published Pirelli tyre strategy matches the actual tyre strategy.");
});

test("dry tyre requirement text warns only for a server-authored actionable state", () => {
  assert.equal(dryTyreRequirementText({ dryTyreRequirement: "UNSATISFIED" }), "Another dry compound required");
  assert.equal(dryTyreRequirementText({ dryTyreRequirement: "SATISFIED" }), "Dry tyre requirement satisfied");
  assert.equal(dryTyreRequirementText({ dryTyreRequirement: "NOT_APPLICABLE" }), null);
  assert.equal(dryTyreRequirementText({ dryTyreRequirement: "UNKNOWN" }), null);
});

test("driver Pirelli badges retain non-directional compound order", () => {
  const baseline = pirelliBaseline({ options: [{ id: "any", rank: "UNRANKED", order: "ANY_ORDER", stopCount: 1, compounds: ["MEDIUM", "HARD"], pitWindows: [null] }] });
  const driver = { pirelliAssessment: "NOT_COMPARABLE", pirelliSummary: "Published Pirelli compounds are available as pre-race reference.", pirelliReferences: [{ optionId: "any", status: "NOT_COMPARABLE", stopComparisons: [{ stopIndex: 0, actualLap: null, publishedStartLap: null, publishedEndLap: null, status: "NO_PUBLISHED_LAP" }] }] };
  const row = driverPirelliReferenceRows(baseline, driver)[0];

  assert.equal(row.ordered, false);
  assert.equal(row.sequence, "M + H");
});

test("display-only Pirelli references never expose a timing verdict", () => {
  const baseline = pirelliBaseline({ options: [{ id: "mh", rank: "FASTEST_PUBLISHED", order: "ORDERED", stopCount: 1, compounds: ["MEDIUM", "HARD"], pitWindows: [{ startLap: 22, endLap: 28 }] }] });
  const driver = { pirelliAssessment: "REFERENCE_ONLY", pirelliReferences: [{ optionId: "mh", status: "REFERENCE_ONLY", stopComparisons: [{ stopIndex: 0, actualLap: 24, publishedStartLap: 22, publishedEndLap: 28, status: "INSIDE" }] }] };
  const row = driverPirelliReferenceRows(baseline, driver)[0];

  assert.equal(row.assessmentText, "Pre-race reference");
  assert.equal(row.windows[0].range, "Actual L24 · Pirelli L22–28");
  assert.equal(row.windows[0].state, null);
});

test("Pirelli context selection keeps up to five distinct useful categories", () => {
  const selected = prioritizedPirelliContextFacts([
    { category: "WEATHER", statement: "Rain is possible." },
    { category: "COMPOUND_OUTLOOK", statement: "C4 offers the widest working range." },
    { category: "WEATHER", statement: "A shower may arrive late." },
    { category: "STRATEGY_OUTLOOK", statement: "A one-stop strategy is preferred." },
    { category: "DEGRADATION", statement: "Thermal degradation is expected." },
    { category: "TRACK_EVOLUTION", statement: "Grip should improve." },
    { category: "GRIP", statement: "Rear grip is limited." },
  ], 5);

  assert.deepEqual(selected.map((fact) => fact.category), ["COMPOUND_OUTLOOK", "STRATEGY_OUTLOOK", "DEGRADATION", "WEATHER", "TRACK_EVOLUTION"]);
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
