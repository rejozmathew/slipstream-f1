import assert from "node:assert/strict";
import test from "node:test";

import { isCriticalTrackStatus, nextAuthoredState } from "../domain/tvMode.mjs";

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
