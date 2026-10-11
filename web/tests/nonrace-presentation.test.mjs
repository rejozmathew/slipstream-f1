import assert from "node:assert/strict";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { act, createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<div id='root'></div>", { url: "http://localhost" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
const { createRoot } = await import("react-dom/client");
const server = await createServer({ configLoader: "runner", cacheDir: "../.codex-tmp/vite-tests", root: fileURLToPath(new URL("..", import.meta.url)), server: { middlewareMode: true, hmr: false }, appType: "custom" });
after(async () => { await server.close(); dom.window.close(); });
const { EMPTY_RACE_STATE } = await server.ssrLoadModule("/domain/protocol.ts");
const { NonRaceTVFeature, AroundCut, OnTrackNow, SessionLog, BestLapSpread, timedSessionRows, packSpreadLabels } = await server.ssrLoadModule("/components/analysis/NonRaceTVFeature.tsx");
const { QualifyingView } = await server.ssrLoadModule("/views/QualifyingView.tsx");
const { PracticeView } = await server.ssrLoadModule("/views/PracticeView.tsx");
const render = (component, props) => renderToStaticMarkup(createElement(component, props));
const driver = (number, overrides = {}) => ({ number: String(number), code: `D${number}`, name: `Driver ${number}`, team: "Team", team_colour: "0099aa", position: number, best_lap: "1:20.000", last_lap: "1:55.999", activity: "ON_TRACK", status: "RUNNING", source_condition: "RUNNING", classification: null, qualifying_eliminated: false, compound: "SOFT", tyre_age: 3, availability: {}, ...overrides });
const state = (kind = "qualifying", drivers = [driver(1), driver(2), driver(3), driver(4)]) => ({ ...EMPTY_RACE_STATE, session: { ...EMPTY_RACE_STATE.session, layout_family: kind, session_kind: kind === "practice" ? "practice_1" : "qualifying", session_clock: "12:34" }, drivers: Object.fromEntries(drivers.map(item => [item.number, item])) });
const analytics = { qualifying: { status: "AVAILABLE", phase: "Q2", settlement: "RUNNING", sessionClock: "05:00", benchmark: { driverNumber: "1", code: "D1", lapTime: "1:21.000", scope: "SEGMENT" }, cutLine: { advancePosition: 2, status: "AVAILABLE", cutoff: { driverNumber: "2", position: 2, bestLap: "1:21.500" } }, drivers: {
  "1": { scopeBest: "1:21.000", benchmarkDelta: 0, activity: "ON_TRACK", cutState: "ADVANCING" },
  "2": { scopeBest: "1:21.500", benchmarkDelta: .5, activity: "IN_PIT", cutState: "ADVANCING" },
  "3": { scopeBest: "1:21.700", benchmarkDelta: .7, activity: "ON_TRACK", cutState: "BELOW_CUT" },
  "4": { scopeBest: null, benchmarkDelta: null, activity: "ON_TRACK", cutState: "UNKNOWN" },
} } };

test("qualifying spread and cut rows retain the current segment and observed cut boundary", () => {
  const html = render(NonRaceTVFeature, { state: state(), analytics });
  assert.match(html, /Q2 SPREAD/);
  assert.match(html, /SETS CUT/);
  assert.match(html, /−0.500/);
  assert.match(html, /\+0.200/);
  assert.match(html, /NO TIME YET/);
  assert.doesNotMatch(html, /1:20.000|1:55.999/);
  assert.equal(timedSessionRows(state(), analytics)[3].best, null);
  const unknown = render(AroundCut, { state: state(), analytics: null });
  assert.doesNotMatch(unknown, /FIGHT FOR POLE|PROVISIONAL P1|SETS CUT/);
  const incompleteCut = structuredClone(analytics);
  incompleteCut.qualifying.drivers["2"].scopeBest = null;
  incompleteCut.qualifying.drivers["2"].benchmarkDelta = null;
  incompleteCut.qualifying.cutLine.cutoff.bestLap = "8:22.052";
  assert.doesNotMatch(render(AroundCut, { state: state(), analytics: incompleteCut }), /8:22.052|SETS CUT|[+−]0.500/);
});

test("on-track card excludes pit, stopped, eliminated and retired drivers and shows session best", () => {
  const observed = state("practice", [driver(1), driver(2, { activity: "IN_PIT" }), driver(3, { source_condition: "STOPPED" }), driver(4, { classification: "DNF" }), driver(5, { source_condition: "RETIRED_INDICATED" })]);
  const html = render(OnTrackNow, { state: observed });
  const parsed = new JSDOM(html).window.document;
  assert.equal(parsed.querySelectorAll(".nr-ontrack-list li").length, 1);
  assert.match(html, /1:20.000/);
  assert.doesNotMatch(html, /1:55.999/);
  assert.equal(new JSDOM(render(OnTrackNow, { state: state(), analytics })).window.document.querySelectorAll(".nr-ontrack-list li").length, 3);
});

test("completed timed-session results remain in the spread without claiming they are running", () => {
  const observed = state("practice", [driver(1, { classification: "FINISHED" }), driver(2, { classification: "FINISHED", best_lap: "1:20.123", best_lap_delta_to_leader: "+0.123" })]);
  assert.match(render(BestLapSpread, { state: observed }), /D1/);
  assert.match(render(BestLapSpread, { state: observed }), /D2/);
  assert.doesNotMatch(render(OnTrackNow, { state: observed }), /<li>/);
});

test("practice spread uses the authored benchmark delta rather than subtracting lap strings", () => {
  const observed = state("practice", [driver(1), driver(2, { best_lap: "1:21.000", best_lap_delta_to_leader: "+0.750" }), driver(3, { best_lap: "1:22.000" })]);
  const rows = timedSessionRows(observed);
  assert.equal(rows[1].gap, .75);
  assert.equal(rows[2].gap, null);
});

test("session log drops future or superseded evidence and keeps relevant completed lap improvements", () => {
  const event = (id, sequence, overrides = {}) => ({ id, kind: "LAP_IMPROVEMENT", availableSequence: sequence, availableAt: "2026-01-01T12:00:00Z", occurredAt: "2026-01-01T12:00:00Z", driverNumbers: ["1"], data: { sessionBest: true }, title: id, detail: "", phase: null, lap: null, ...overrides });
  const html = render(SessionLog, { state: state("practice"), analytics: { story: { sequence: 5, asOf: "2026-01-01T12:00:00Z", events: [event("old", 1), event("corrected", 2, { supersedes: "old" }), event("future", 6), event("ordinary", 3, { data: { position: 15 } })] } } });
  assert.match(html, /corrected/);
  assert.doesNotMatch(html, />old<|future|ordinary/);
});

test("spread label packing clusters close cars and keeps the followed driver as representative", () => {
  const result = packSpreadLabels([{ key: "1", x: 0, priority: 0, focus: false, label: "ONE" }, { key: "2", x: 4, priority: 1, focus: true, label: "TWO" }, { key: "3", x: 90, priority: 2, focus: false, label: "THR" }], 100);
  assert.equal(result.get("1").show, false);
  assert.equal(result.get("2").show, true);
  assert.equal(result.get("2").count, 2);
  assert.equal(result.get("3").show, true);
  assert.ok(result.get("2").shift > 0);
});

test("phone cut-line and runs tabs expose the reference's session panels and driver actions", async () => {
  const root = createRoot(document.getElementById("root"));
  const selected = [];
  const base = { replayAvailable: true, viewingMode: "replay", positionMode: "unavailable", onSelectDriver: number => selected.push(number), towerView: "standard", onTowerViewChange: () => {} };
  await act(() => root.render(createElement(QualifyingView, { ...base, state: state(), analytics })));
  await act(() => [...document.querySelectorAll(".mobile-priority-tabs button")].find(button => button.textContent === "CUT LINE").click());
  assert.match(document.querySelector(".phone-timed-session").textContent, /Around the cut/);
  assert.ok(document.querySelector(".phone-timed-session .nr-cut"));
  await act(() => document.querySelector(".phone-timed-session .nr-zone-list button").click());
  assert.deepEqual(selected, ["1"]);
  await act(() => root.render(createElement(PracticeView, { ...base, state: state("practice"), analytics: null })));
  await act(() => [...document.querySelectorAll(".mobile-priority-tabs button")].find(button => button.textContent === "RUNS").click());
  assert.match(document.querySelector(".phone-timed-session").textContent, /REMAINING12:34/);
  assert.ok(document.querySelector(".phone-timed-session .nr-session-log"));
  assert.ok(document.querySelector(".phone-timed-session .nr-ontrack"));
  await act(() => root.unmount());
});
