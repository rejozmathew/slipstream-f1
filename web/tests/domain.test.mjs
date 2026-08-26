import assert from "node:assert/strict";
import test from "node:test";

import { isCriticalTrackStatus, nextAuthoredState } from "../domain/tvMode.mjs";
import {
  battleFactorPresentation,
  battleGapPresentation,
  gapChartModel,
  paceChartAvailability,
  trackCoverage,
} from "../domain/correctness.mjs";

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
    { number: "1", code: "NOR", position: 1, track_position: 0.4 },
    { number: "2", code: "VER", position: 2, track_position: null },
    { number: "3", code: "PIA", position: null, track_position: null },
  ], "timing_estimate");
  assert.deepEqual(coverage, {
    classified: 2,
    positioned: 1,
    unpositioned: 1,
    unpositionedLabels: ["VER"],
  });
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
