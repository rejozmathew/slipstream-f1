import assert from "node:assert/strict";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import { JSDOM } from "jsdom";

const server = await createServer({ configLoader: "runner", cacheDir: "../.codex-tmp/vite-tests", root: fileURLToPath(new URL("..", import.meta.url)), server: { middlewareMode: true, hmr: false }, appType: "custom" });
after(() => server.close());
const { EMPTY_RACE_STATE } = await server.ssrLoadModule("/domain/protocol.ts");
const { BattleComposition, commonBattleLaps } = await server.ssrLoadModule("/components/battle/BattleComposition.tsx");
const { StrategyPitBoard, StrategyStintChart, observedStintSegments } = await server.ssrLoadModule("/components/analysis/StrategyPitBoard.tsx");
const render = (component, props) => renderToStaticMarkup(createElement(component, props));
const driver = (number, overrides = {}) => ({ number: String(number), code: `D${number}`, name: `Driver ${number}`, team: "Team", team_colour: "0099aa", position: number, lap: 20, best_lap: "1:20.000", last_lap: "1:25.000", gap_to_leader: String(number * 100), activity: "ON_TRACK", status: "RUNNING", source_condition: "RUNNING", classification: null, compound: "HARD", tyre_age: 3, pit_count: 8, availability: {}, ...overrides });
const first = driver(1), second = driver(3);
const state = { ...EMPTY_RACE_STATE, session: { ...EMPTY_RACE_STATE.session, layout_family: "race", session_kind: "race", lap: 20, total_laps: 70 }, drivers: { "1": first, "3": second } };
const sample = (lap, rawLapTime, extra = {}) => ({ lap, rawLapTime, quality: "representative", contaminationReasons: [], ...extra });
const analytics = { publishedStrategy: { drivers: { "1": { actualStrategy: { completedStops: 1, compounds: ["MEDIUM", "HARD"], stopLaps: [12], evidenceComplete: true } }, "3": { actualStrategy: { completedStops: 2, compounds: ["MEDIUM", "MEDIUM", "HARD"], stopLaps: [5, 10], evidenceComplete: true } } } }, battle: { candidates: [], pairs: { "1:3": { aheadDriverNumber: "1", behindDriverNumber: "3", gapSeconds: 4.321, gapBasis: "leader_gap_difference", comparisonState: "COMPARABLE" } }, histories: { "1:3": [{ lap: 15, gapSeconds: 4 }, { lap: 16, gapSeconds: 4.1 }, { lap: 17, gapSeconds: 4.3 }] } }, drivers: {
  "1": { pace: { samples: [sample(18, 80), sample(19, 110, { quality: "contaminated", contaminationReasons: ["PIT_IN"] }), sample(20, 81)] }, pitEvents: [{ driverNumber: "1", sequence: 1, occurredAt: "2026-01-01T12:00:00Z", lap: 12, previousCompound: "MEDIUM", newCompound: "HARD", pitLaneDuration: 22, stopDuration: 2.1 }] },
  "3": { pace: { samples: [sample(18, 80.5), sample(19, 82), sample(20, 81.2, { quality: "unknown" })] }, pitEvents: [] },
} };

test("battle hero orders a reversed pinned pair and uses server pair gap with nonadjacent semantics", () => {
  const html = render(BattleComposition, { state, analytics, pair: [second, first] });
  assert.match(html, /P1 VS P3 · NOT ADJACENT/);
  assert.match(html, />4.321</);
  assert.match(html, /D3 BEHIND D1/);
  assert.match(html, /GAP AT EACH LAP/);
  assert.match(html, /OPENING/);
  assert.doesNotMatch(html, />200.000</);
  assert.match(html, /1 stop/);
  assert.doesNotMatch(html, /8 stops/);
  const missing = render(BattleComposition, { state, pair: [first, second], analytics: { ...analytics, battle: { ...analytics.battle, pairs: { "1:3": { ...analytics.battle.pairs["1:3"], comparisonState: "NOT_COMPARABLE", gapSeconds: null, reason: "Different known laps" } } } } });
  assert.match(missing, /Different known laps/);
  assert.doesNotMatch(missing, />4.321</);
});

test("lap comparison labels pit and nonrepresentative laps without declaring a faster driver", () => {
  const laps = commonBattleLaps(analytics, first, second, 6);
  assert.equal(laps.find(row => row.first.lap === 18).delta, .5);
  assert.equal(laps.find(row => row.first.lap === 19).pit, true);
  assert.equal(laps.find(row => row.first.lap === 19).delta, null);
  assert.equal(laps.find(row => row.first.lap === 20).delta, null);
  const parsed = new JSDOM(render(BattleComposition, { state, analytics, pair: [first, second], posture: "tv" })).window.document;
  assert.equal(parsed.querySelectorAll(".bc-faster").length, 1);
  assert.match(parsed.querySelector(".bc-laps").textContent, /PIT LAP/);
  assert.match(parsed.querySelector(".bc-laps").textContent, /NON-REP/);
});

test("pit board counts completed observations and preserves unknown destination compounds", () => {
  const inPit = driver(1, { activity: "IN_PIT", source_condition: "IN_PIT" });
  const pending = { ...analytics, publishedStrategy: { drivers: {} }, drivers: { "1": { pitEvents: [] }, "3": { pitEvents: [{ driverNumber: "3", sequence: 3, occurredAt: "2026-01-01T12:03:00Z", lap: 18, previousCompound: "MEDIUM", newCompound: null, pitLaneDuration: null }] } } };
  const html = render(StrategyPitBoard, { state: { ...state, drivers: { "1": inPit, "3": second } }, analytics: pending });
  assert.match(html, /STOPS COMPLETED/);
  assert.match(html, /0 STOPS/);
  assert.match(html, /1 STOP/);
  assert.doesNotMatch(html, /3\+ STOPS/);
  const parsed = new JSDOM(html).window.document;
  assert.equal(parsed.querySelectorAll(".spb-lane button").length, 1);
  assert.ok(parsed.querySelector(".spb-stops .compound-unknown"));
  assert.match(parsed.querySelector(".spb-stops").textContent, /LANE TIME UNKNOWN/);
});

test("stint bars keep same-compound stop boundaries and stop at the observed cursor", () => {
  const segments = observedStintSegments(second, analytics, 20);
  assert.deepEqual(segments.map(segment => [segment.compound, segment.start, segment.end]), [["MEDIUM", 0, 5], ["MEDIUM", 5, 10], ["HARD", 10, 20]]);
  const retired = observedStintSegments({ ...second, classification: "DNF", lap: 16 }, analytics, 20);
  assert.equal(retired.at(-1).end, 16);
  const incomplete = { ...analytics, publishedStrategy: { drivers: { "3": { actualStrategy: { ...analytics.publishedStrategy.drivers["3"].actualStrategy, evidenceComplete: false } } } } };
  assert.equal(observedStintSegments(second, incomplete, 20)[0].start, 5);
  const missingBoundary = { ...analytics, publishedStrategy: { drivers: { "3": { actualStrategy: { ...analytics.publishedStrategy.drivers["3"].actualStrategy, stopLaps: [5, null] } } } } };
  assert.deepEqual(observedStintSegments(second, missingBoundary, 20).map(segment => [segment.start, segment.end]), [[0, 5]]);
  const html = render(StrategyStintChart, { state, analytics });
  assert.match(html, /Stints by lap/);
  assert.match(html, /HARD · laps 10–20/);
  assert.doesNotMatch(html, /laps 10–70/);
});
