import assert from "node:assert/strict";
import test from "node:test";

import { advanceBattleRecommendation } from "../domain/battleHysteresis.mjs";
import { isCriticalTrackStatus, nextAuthoredState } from "../domain/tvMode.mjs";

const pair = (ahead, behind, score) => ({ aheadDriverNumber: ahead, behindDriverNumber: behind, score });

test("recommended battle holds until source-time hysteresis and score margin are met", () => {
  const initial = advanceBattleRecommendation(null, pair("1", "2", 50), 1_000);
  const tooSoon = advanceBattleRecommendation(initial, pair("3", "4", 80), 10_000, 20, 8);
  const tooSmall = advanceBattleRecommendation(initial, pair("3", "4", 56), 25_000, 20, 8);
  const switched = advanceBattleRecommendation(initial, pair("3", "4", 60), 25_000, 20, 8);

  assert.deepEqual(tooSoon, initial);
  assert.deepEqual(tooSmall, initial);
  assert.deepEqual(switched.candidate, pair("3", "4", 60));
});

test("recommended battle switches immediately when the held pair is no longer valid", () => {
  const initial = { candidate: pair("1", "2", 80), since: 1_000 };
  const switched = advanceBattleRecommendation(initial, pair("3", "4", 20), 2_000, 20, 8, false);

  assert.deepEqual(switched.candidate, pair("3", "4", 20));
});

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
