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
  driverPublishedRouteRows,
  driverPublishedRoutesText,
  driverPublishedWindowsText,
  driverStrategyRelationship,
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

test("Australia and Canada context-only publications stay present without inventing routes", () => {
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
  assert.equal(driverPublishedRoutesText(australia), "No specific route published");
  assert.equal(driverStrategyRelationship(canada), NO_SPECIFIC_PIRELLI_STRATEGY);
  assert.equal(prioritizedPirelliContextFacts(canada.contextFacts, 1)[0].category, "STRATEGY_OUTLOOK");
});

test("Miami driver presentation resolves the actual route and window without exposing option ids", () => {
  const miami = pirelliBaseline({ options: [{ id: "option-1", rank: "FASTEST_PUBLISHED", order: "ORDERED", stopCount: 1, compounds: ["MEDIUM", "HARD"], pitWindows: [{ startLap: 22, endLap: 28 }] }] });
  const driver = { relation: "MATCHING_ONE", compatibleOptionIds: ["option-1"], observedCompounds: ["MEDIUM"], windows: [{ optionId: "option-1", stopIndex: 0, startLap: 22, endLap: 28, state: "COMPLETED" }] };
  const rows = driverPublishedRouteRows(miami, driver, [{ ordinal: 1, lap: 24 }]);

  assert.equal(driverPublishedRoutesText(miami, driver), "M → H");
  assert.equal(driverPublishedWindowsText(miami, driver), "L22–28");
  assert.match(driverStrategyRelationship(miami, driver), /M → H tyre strategy/);
  assert.equal(rows[0].windows[0].state, "Observed stop L24");
  assert.doesNotMatch(`${driverPublishedRoutesText(miami, driver)} ${driverPublishedWindowsText(miami, driver)}`, /option-1|MATCHING_ONE|COMPLETED/);
});

test("Dutch presentation preserves distinct routes, windows, and non-directional compound orders", () => {
  const dutch = pirelliBaseline({ options: [
    { id: "mh", rank: "FASTEST_PUBLISHED", order: "ORDERED", stopCount: 1, compounds: ["MEDIUM", "HARD"], pitWindows: [{ startLap: 27, endLap: 33 }] },
    { id: "sh", rank: "ALTERNATIVE", order: "ORDERED", stopCount: 1, compounds: ["SOFT", "HARD"], pitWindows: [{ startLap: 26, endLap: 32 }], publishedDeltaSeconds: 1.0 },
  ] });
  const driver = { relation: "MATCHING_MULTIPLE", compatibleOptionIds: ["mh", "sh"], observedCompounds: ["MEDIUM"], windows: [] };
  assert.equal(driverPublishedRoutesText(dutch, driver), "M → H / S → H");
  assert.equal(driverPublishedWindowsText(dutch, driver), "M → H: L27–33 · S → H: L26–32");
  assert.equal(driverStrategyRelationship(dutch, driver), "Current path remains compatible with 2 published tyre strategies.");
  assert.equal(optionDeltaText(dutch.options[1]), "Published delta · +1.0s");
  assert.equal(optionOrderNote({ order: "ANY_ORDER", compounds: ["MEDIUM", "HARD"] }), "Compounds may be used in either order.");
});

test("a diverged driver gets neutral wording instead of an internal relation label", () => {
  const baseline = pirelliBaseline({ options: [{ id: "mh", rank: "FASTEST_PUBLISHED", order: "ORDERED", stopCount: 1, compounds: ["MEDIUM", "HARD"], pitWindows: [{ startLap: 22, endLap: 28 }] }] });
  const driver = { relation: "DIVERGED", compatibleOptionIds: [], observedCompounds: ["SOFT", "MEDIUM"], windows: [] };
  assert.equal(driverStrategyRelationship(baseline, driver), "No published Pirelli tyre strategy matches the current path.");
});

test("Pirelli context selection keeps up to five distinct useful categories", () => {
  const selected = prioritizedPirelliContextFacts([
    { category: "WEATHER", statement: "Rain is possible." },
    { category: "COMPOUND_OUTLOOK", statement: "C4 offers the widest working range." },
    { category: "WEATHER", statement: "A shower may arrive late." },
    { category: "STRATEGY_OUTLOOK", statement: "A one-stop route is preferred." },
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
