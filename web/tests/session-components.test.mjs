import assert from "node:assert/strict";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { act, createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import { JSDOM } from "jsdom";

import { formatLiveDelay, LIVE_DELAY_PRESETS, parseLiveDelay } from "../domain/liveDelay.mjs";

const dom = new JSDOM("<div id='test-root'></div>", { url: "http://localhost" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import("react-dom/client");
after(() => dom.window.close());

const server = await createServer({ configLoader: "runner", cacheDir: "../.codex-tmp/vite-tests", root: fileURLToPath(new URL("..", import.meta.url)), server: { middlewareMode: true, hmr: false }, appType: "custom" });
after(() => server.close());
const { EMPTY_RACE_STATE } = await server.ssrLoadModule("/domain/protocol.ts");
const { TrackMap } = await server.ssrLoadModule("/components/analysis/TrackMap.tsx");
const { LiveControls } = await server.ssrLoadModule("/components/shell/LiveControls.tsx");
const { ReplayRecordingNotice } = await server.ssrLoadModule("/components/shell/ReplayRecordingNotice.tsx");
const { SessionStrip } = await server.ssrLoadModule("/components/shell/SessionStrip.tsx");
const { SessionProgress } = await server.ssrLoadModule("/components/shared/SessionProgress.tsx");
const { TimingTower } = await server.ssrLoadModule("/components/timing/TimingTower.tsx");
const { DriverFocusView } = await server.ssrLoadModule("/views/DriverFocusView.tsx");
const { QualifyingView } = await server.ssrLoadModule("/views/QualifyingView.tsx");
const { useProductPreferences } = await server.ssrLoadModule("/hooks/useProductPreferences.ts");
const render = (component, props) => renderToStaticMarkup(createElement(component, props));
const driver = {
  number: "1", code: "ONE", name: "Driver One", team: "Team", position: 3, lap: 12,
  compound: "SOFT", tyre_age: 5, stint_laps: 5, pit_count: 2,
  gap_to_leader: "+0.685", last_lap: "1:24.123", best_lap: "1:23.456",
  best_lap_delta_to_ahead: "+0.249",
  source_condition: "RUNNING", status: "RUNNING", activity: "ON_TRACK",
  classification: null, availability: {}, track_position: null, x: null, y: null,
};

test("partial recording notice requires explicit incomplete metadata, independent of cursor", () => {
  const metadata = { available: true, complete: false };
  const html = render(ReplayRecordingNotice, { metadata });
  assert.match(html, /role="status"/);
  assert.match(html, /PARTIAL RECORDING/);
  assert.match(html, /Session completion is not recorded/);
  assert.doesNotMatch(html, /button|PACKETS LOST|CORRUPT/);
  for (const absent of [null, { available: true }, { available: true, complete: null }, { available: true, complete: true }, { available: false, complete: false }]) {
    assert.equal(render(ReplayRecordingNotice, { metadata: absent }), "");
  }
});

test("TrackMap has explicit Live/Replay absence and approximate-only position labels", () => {
  const props = { session: EMPTY_RACE_STATE.session, circuit: { ...EMPTY_RACE_STATE.circuit, path: [[0, 0], [10, 0], [5, 10]] }, drivers: [driver], positionMode: "unavailable" };
  const live = render(TrackMap, { ...props, viewingMode: "live" });
  assert.match(live, /CAR POSITION NOT AVAILABLE IN PUBLIC LIVE FEED/);
  assert.doesNotMatch(live, /FOR THIS REPLAY/);
  assert.match(render(TrackMap, { ...props, viewingMode: "replay" }), /CAR POSITION NOT AVAILABLE FOR THIS REPLAY/);
  const estimate = render(TrackMap, { ...props, viewingMode: "live", positionMode: "timing_estimate", drivers: [{ ...driver, track_position: 0.5 }] });
  assert.match(estimate, /POSITION · APPROX · TIMING-DERIVED/);
  assert.match(estimate, /class="car-marker/);
  assert.doesNotMatch(estimate, /CAR POSITION NOT|GPS|SOURCE X\/Y|PRECISE/);
});

test("Practice renders normalized GAP, factual statuses and quiet running rows", () => {
  const html = render(TimingTower, { variant: "practice", replayAvailable: true, drivers: [
    { ...driver, position: 1, best_lap_delta_to_ahead: null }, { ...driver, number: "2", source_condition: "IN_PIT" },
    { ...driver, number: "3", source_condition: "STOPPED" },
    { ...driver, number: "4", classification: "DNF" },
  ] });
  for (const label of ["GAP", "STOPS", "STATUS", "+0.249", "IN PIT", "STOPPED", "DNF"]) assert.ok(html.includes(label), label);
  assert.match(html, /title="Best-lap difference to the driver above\."/);
  assert.doesNotMatch(html, /BENCHMARK|\+0\.685/);
  assert.match(html, /class="practice-driver-status"><\/span>/);
  assert.doesNotMatch(html, />PIT<|NO_RECENT_PROGRESS/);
});

test("Practice Driver Focus cannot render actionable Race strategy even with a mismatched sidecar", () => {
  const props = { state: { ...EMPTY_RACE_STATE, session: { ...EMPTY_RACE_STATE.session, session_kind: "practice_2", layout_family: "practice" }, drivers: { "1": driver } }, sessionLayout: "practice", driverNumber: "1", history: null, historyError: null, playhead: null, positionMode: "unavailable", viewingMode: "live", onChangeDriver() {}, onBack() {}, analytics: { drivers: {}, publishedStrategy: { baseline: { status: "ABSENT", tyreBank: { drivers: {} } }, drivers: { "1": { dryTyreRequirement: "UNSATISFIED" } } } } };
  const practice = render(DriverFocusView, props);
  assert.doesNotMatch(practice, /PIRELLI|Another dry compound|required|Dry tyre requirement|DRIVER STRATEGY/);
  for (const label of ["Current stint", "Pit history", "Stint trend", "Conditions"]) assert.ok(practice.includes(label), label);
  const race = render(DriverFocusView, { ...props, sessionLayout: "race", state: { ...props.state, session: { ...props.state.session, session_kind: "race", layout_family: "race" } } });
  assert.match(race, /Another dry compound required/);
});

test("Race Timing adds a source interval alongside the leader gap without changing other modes", () => {
  const props = { variant: "race", mode: "timing", replayAvailable: true, intervalsAvailable: true, drivers: [
    { ...driver, position: 1, interval_to_ahead: "+99.999" },
    { ...driver, number: "2", position: 2, interval_to_ahead: "+0.123" },
    { ...driver, number: "3", position: 3, interval_to_ahead: null },
    { ...driver, number: "4", position: 4, interval_to_ahead: "+77.777", classification: "DNF" },
    { ...driver, number: "5", position: 5, interval_to_ahead: "+1 LAP", gap_to_leader: "+1 LAP" },
    { ...driver, number: "6", position: 6, interval_to_ahead: "+1.234", classification: "FINISHED" },
  ] };
  const html = render(TimingTower, props);
  const root = new JSDOM(html);
  const rows = [...root.window.document.querySelectorAll("button[role=row]")];
  assert.match(html, /title="Interval to the driver immediately above in the classification\."/);
  assert.match(html, />INT</);
  assert.match(html, /\+0\.685/);
  assert.deepEqual(rows.map((row) => row.children[3].textContent), ["—", "+0.123", "—", "—", "+1 LAP", "+1.234"]);
  assert.equal(rows[3].children[2].textContent, "DNF");
  assert.equal(rows[5].children[2].textContent, "FINISHED");
  assert.ok(rows.every((row) => row.children.length === 10));
  root.window.close();
  assert.doesNotMatch(render(TimingTower, { ...props, intervalsAvailable: false }), />INT<|\+0\.123/);
  for (const mode of ["standard", "strategy"]) assert.doesNotMatch(render(TimingTower, { ...props, mode }), />INT<|\+0\.123/);
});

test("source countdown is shared, kind-aware and never synthesized from session duration", () => {
  const session = { ...EMPTY_RACE_STATE.session, session_kind: "practice_2", session_clock: "00:42:17", session_clock_running: false };
  const strip = render(SessionStrip, { session, selected: null, viewingMode: "live", livePhase: "LIVE", liveNow: true, onGoLive() {} });
  assert.match(strip, /REMAINING/);
  assert.match(strip, /42:17/);
  assert.doesNotMatch(strip, />LAP</);
  assert.equal(render(SessionProgress, { session }), render(SessionProgress, { session: { ...session, session_clock_running: true } }), "running changes do not create a browser clock");
  assert.match(render(SessionProgress, { session: { ...session, session_clock: null } }), /REMAINING.*—/);
  for (const [kind, prefix] of [["qualifying", "Q"], ["sprint_qualifying", "SQ"]]) for (const phase of [1, 2, 3]) {
    const progress = render(SessionProgress, { session: { ...session, session_kind: kind, qualifying_phase: `${prefix}${phase}` } });
    assert.match(progress, new RegExp(`session-progress-phase[^>]*>${prefix}${phase}.*42:17`));
  }
  for (const kind of ["race", "sprint"]) {
    const race = render(SessionProgress, { session: { ...session, session_kind: kind, lap: 27, total_laps: 53 } });
    assert.match(race, /LAP.*27 \/ 53/);
    assert.doesNotMatch(race, /42:17|REMAINING/);
  }
  assert.match(render(SessionProgress, { session: { ...session, session_kind: "unknown" } }), /SESSION.*—/);
});

test("precise Live delay accepts exact M:SS, rejects invalid values, and renders server truth", () => {
  assert.deepEqual(LIVE_DELAY_PRESETS, [5, 10, 30, 60, 120, 180, 300]);
  for (const [input, seconds] of [["0:45", 45], ["1:08", 68], ["2:17", 137], ["5:00", 300], ["0:00", 0]]) assert.equal(parseLiveDelay(input), seconds);
  for (const invalid of ["5:01", "6:00", "1:60", "-1:00", "NaN", "Infinity", "2:7", "137", "", "1:08x"]) assert.equal(parseLiveDelay(invalid), null);
  assert.equal(formatLiveDelay(137), "2:17");
  const props = { phase: "LIVE", commandAvailable: true, onCommand() { return true; } };
  const delayed = render(LiveControls, { ...props, delaySeconds: 137 });
  assert.match(delayed, /DELAY 2:17/);
  assert.match(delayed, /GO LIVE/);
  assert.match(delayed, /<form/);
  assert.match(delayed, /type="submit"/);
  assert.doesNotMatch(delayed, />0s</);
  assert.match(render(LiveControls, { ...props, delaySeconds: 60 }), /class="active"[^>]*>1m</);
  assert.match(render(LiveControls, { ...props, delaySeconds: 300 }), /DELAY 5:00/);
  const current = render(LiveControls, { ...props, delaySeconds: 0 });
  assert.match(current, /aria-live="polite">LIVE</);
  assert.doesNotMatch(current, /DELAY 2:17/);
});

test("Live delay handlers submit presets/custom input, reject invalid input and await server confirmation", async () => {
  const container = document.getElementById("test-root");
  const root = createRoot(container);
  const commands = [];
  const props = { phase: "LIVE", commandAvailable: true, onCommand(command) { commands.push(command); return true; } };
  const update = async (seconds) => act(() => root.render(createElement(LiveControls, { ...props, delaySeconds: seconds })));
  const button = (label) => [...container.querySelectorAll("button")].find((item) => item.textContent === label);
  const submit = async (value) => {
    const input = container.querySelector("input");
    await act(() => {
      Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(input, value);
      input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
    });
    await act(() => container.querySelector("form").requestSubmit());
  };
  try {
    await update(0);
    assert.equal(container.querySelector("input").value, "0:00");
    await act(() => button("2m").click());
    assert.deepEqual(commands.at(-1), { type: "delay", seconds: 120 });
    assert.equal(container.querySelector("[aria-live]").textContent, "LIVE");
    await update(120);
    assert.equal(container.querySelector("input").value, "2:00");
    assert.equal(container.querySelector("[aria-live]").textContent, "DELAY 2:00");
    await submit("2:17");
    assert.deepEqual(commands.at(-1), { type: "delay", seconds: 137 });
    await update(30);
    assert.equal(container.querySelector("input").value, "0:30");
    assert.equal(container.querySelector("[aria-live]").textContent, "DELAY 0:30", "server truth can differ from the request");
    await update(137);
    const count = commands.length;
    await submit("5:01");
    assert.equal(commands.length, count);
    assert.match(container.querySelector("[role=alert]").textContent, /0:00 to 5:00/);
    await submit("5:00");
    assert.deepEqual(commands.at(-1), { type: "delay", seconds: 300 });
    await update(300);
    await act(() => button("GO LIVE").click());
    assert.deepEqual(commands.at(-1), { type: "reset" });
    assert.equal(container.querySelector("[aria-live]").textContent, "DELAY 5:00");
    await update(0);
    assert.equal(container.querySelector("input").value, "0:00");
    assert.equal(container.querySelector("[aria-live]").textContent, "LIVE");
  } finally {
    await act(() => root.unmount());
  }
});


test("Practice GAP compares P1 while INT preserves the adjacent best-lap difference", () => {
  const html = render(TimingTower, { variant: "practice", replayAvailable: true, drivers: [
    { ...driver, position: 1, best_lap_delta_to_leader: null, best_lap_delta_to_ahead: null },
    { ...driver, number: "16", position: 2, best_lap_delta_to_leader: "+0.113", best_lap_delta_to_ahead: "+0.113" },
    { ...driver, number: "44", position: 3, best_lap_delta_to_leader: "+0.149", best_lap_delta_to_ahead: "+0.036" },
    { ...driver, number: "4", position: 4, best_lap_delta_to_leader: null, best_lap_delta_to_ahead: null },
  ] });
  const root = new JSDOM(html);
  try {
    const rows = [...root.window.document.querySelectorAll("button[role=row]")];
    assert.deepEqual(rows.map(row => row.children[6].textContent), ["—", "+0.113", "+0.149", "—"]);
    assert.deepEqual(rows.map(row => row.children[7].textContent), ["—", "+0.113", "+0.036", "—"]);
    assert.ok(rows.every(row => row.children.length === 11));
    assert.match(html, /title="Best-lap gap to the leader \(P1\)\."/);
    assert.match(html, />INT</);
    assert.doesNotMatch(html, /BENCHMARK|\+0\.685/);
  } finally { root.window.close(); }
});

test("Madring reference is scoped to 2026, yields to geometry and never positions cars", () => {
  const props = { session: { ...EMPTY_RACE_STATE.session, circuit: "Madring", started_at: "2026-09-11T15:00:00Z", session_kind: "race" }, circuit: EMPTY_RACE_STATE.circuit, drivers: [{ ...driver, track_position: 0.5 }], positionMode: "timing_estimate", viewingMode: "live" };
  const html = render(TrackMap, props);
  assert.match(html, /alt="Madring 2026 official circuit map"/);
  assert.match(html, /Official circuit map · Formula 1/);
  assert.match(html, /REFERENCE MAP · CAR POSITIONS UNAVAILABLE/);
  assert.match(html, /ACTIVE COVERAGE · 0\/1/);
  assert.doesNotMatch(html, /class="car-marker|class="map-center|POSITION · APPROX|SHAPE · OBSERVED/);
  for (const session of [{ ...props.session, circuit: "Barcelona" }, { ...props.session, started_at: "2027-09-11T15:00:00Z" }, { ...props.session, started_at: null }]) {
    assert.doesNotMatch(render(TrackMap, { ...props, session }), /<img|Official circuit map/);
  }
  const withGeometry = render(TrackMap, { ...props, circuit: { ...props.circuit, path: [[0, 0], [10, 0], [5, 10]] } });
  assert.match(withGeometry, /class="car-marker/);
  assert.doesNotMatch(withGeometry, /<img|REFERENCE MAP/);
});

test("failed reference image retains the official source link", async () => {
  const container = document.getElementById("test-root");
  const root = createRoot(container);
  try {
    await act(() => root.render(createElement(TrackMap, {
      session: { ...EMPTY_RACE_STATE.session, circuit: "Madring", started_at: "2026-09-11T15:00:00Z" },
      circuit: EMPTY_RACE_STATE.circuit, drivers: [], positionMode: "unavailable", viewingMode: "live",
    })));
    await act(() => container.querySelector("img").dispatchEvent(new dom.window.Event("error")));
    assert.equal(container.querySelector("img"), null);
    assert.match(container.textContent, /MAP IMAGE UNAVAILABLE/);
    assert.match(container.querySelector("a").href, /^https:\/\/www.formula1.com\//);
  } finally { await act(() => root.unmount()); }
});


const qualifyingAnalytics = (phase = "Q2", final = false) => ({
  sessionKind: phase.startsWith("SQ") ? "sprint_qualifying" : "qualifying",
  qualifying: { status: "AVAILABLE", phase, final, sessionClock: null,
    cutLine: { status: "AVAILABLE", advancePosition: 16 },
    benchmark: { driverNumber: "2", scope: "SEGMENT" },
    drivers: { "1": { scopeBest: "1:21.444", benchmarkDelta: 0.456, intervalToAhead: 0.123,
      segmentResults: [83.111, 82.222, 81.333], qStatus: "OUT Q2",
      latestLap: { lapTime: 84, sector1: 99.999, sector2: 99.999, sector3: 99.999 },
      scopeLatestLap: { lapTime: 84, sector1: 26.111, sector2: 28.222, sector3: 29.667 },
    } },
  },
});
const tableHeaders = (html) => [...new JSDOM(html).window.document.querySelectorAll('.timing-header > span')].map((node) => node.textContent);

test("Qualifying Standard separates result history from active Timing detail for all six segments", () => {
  for (const prefix of ["Q", "SQ"]) for (const segment of [1, 2, 3]) {
    const phase = `${prefix}${segment}`;
    const props = { variant: "qualifying", drivers: [driver], replayAvailable: true, sectorTimingAvailable: true, analytics: qualifyingAnalytics(phase) };
    const standard = render(TimingTower, props);
    assert.deepEqual(tableHeaders(standard), ["P", "DRIVER / TEAM", `${prefix}1`, `${prefix}2`, `${prefix}3`, "GAP", "INT", "TYRE", "AGE", "STATUS"]);
    for (const value of ["1:23.111", "1:22.222", "1:21.333", "+0.456", "+0.123", "5L", "ON TRACK", "OUT Q2"]) assert.ok(standard.includes(value), value);
    assert.doesNotMatch(standard, /26\.111|99\.999|1:21\.444/);
    const timing = render(TimingTower, { ...props, mode: "timing" });
    assert.deepEqual(tableHeaders(timing), ["P", "DRIVER / TEAM", phase, "S1", "S2", "S3", "GAP", "INT", "TYRE", "STATUS"]);
    for (const value of ["1:21.444", "26.111", "+0.456", "+0.123", "ON TRACK", "OUT Q2"]) assert.ok(timing.includes(value), value);
    assert.doesNotMatch(timing, /1:23\.111|1:22\.222|1:21\.333|99\.999|5L|\+0\.685/);
  }
});

test("Qualifying Timing supports absent sectors, missing scope data and final classifications", () => {
  const analytics = qualifyingAnalytics("Q3", true);
  const model = analytics.qualifying.drivers["1"];
  Object.assign(model, { scopeBest: null, scopeLatestLap: null, benchmarkDelta: null, intervalToAhead: null });
  const props = { variant: "qualifying", mode: "timing", drivers: [driver], replayAvailable: true, analytics };
  const absent = render(TimingTower, props);
  assert.deepEqual(tableHeaders(absent), ["P", "DRIVER / TEAM", "Q3", "GAP", "INT", "TYRE", "STATUS", "Q STATUS"]);
  assert.match(absent, /QUALIFYING FINAL/);
  assert.match(absent, /OUT Q2/);
  const missing = render(TimingTower, { ...props, sectorTimingAvailable: true });
  assert.ok(tableHeaders(missing).includes("S1"));
  assert.doesNotMatch(missing, /UNKNOWN|UNAVAILABLE/);
  assert.doesNotMatch(missing, /99\.999|26\.111|1:21\.444|\+0\.456|\+0\.123/);
  analytics.qualifying.phase = "UNKNOWN";
  assert.ok(tableHeaders(render(TimingTower, props)).includes("BEST"));
  // Tied laps and an overtaken classification update retain numeric zero/negative intervals.
  model.intervalToAhead = 0;
  assert.match(render(TimingTower, props), /\+0\.000/);
  model.intervalToAhead = -0.123;
  const negative = render(TimingTower, props);
  assert.match(negative, />-0\.123</);
  assert.doesNotMatch(negative, /\+-/);
});

test("Qualifying status follows observed lifecycle in both modes without inferring from silence", () => {
  const examples = [
    [{ source_condition: "RUNNING", activity: "ON_TRACK" }, "ON TRACK"],
    [{ source_condition: "RUNNING", activity: "IN_PIT" }, "IN PIT"],
    [{ source_condition: "STOPPED", activity: "ON_TRACK" }, "STOPPED"],
    [{ source_condition: "RETIRED_INDICATED", activity: "ON_TRACK" }, "RETIRED"],
    [{ classification: "DNF", activity: "ON_TRACK" }, "DNF"],
    [{ source_condition: "UNKNOWN", status: "UNKNOWN", activity: "UNKNOWN" }, "—"],
  ];
  for (const mode of ["standard", "timing"]) for (const [facts, label] of examples) {
    const html = render(TimingTower, { variant: "qualifying", mode, replayAvailable: true, drivers: [{ ...driver, ...facts }], analytics: qualifyingAnalytics() });
    const status = new JSDOM(html).window.document.querySelector('.qualifying-driver-status');
    assert.equal(status.textContent, label);
  }
});

function QualifyingPreferenceHarness(props) {
  const preferences = useProductPreferences();
  return createElement(QualifyingView, { ...props, towerView: preferences.qualifyingTowerView, onTowerViewChange: preferences.setQualifyingTowerView });
}

test("Qualifying mode switches both desktop and mobile towers and survives incoming data", async () => {
  const container = document.getElementById("test-root");
  const root = createRoot(container);
  const props = { state: { ...EMPTY_RACE_STATE, drivers: { "1": driver } }, analytics: qualifyingAnalytics(), replayAvailable: true, sectorTimingAvailable: true, positionMode: "unavailable", viewingMode: "live", onSelectDriver() {} };
  try {
    await act(async () => root.render(createElement(QualifyingPreferenceHarness, props)));
    const controls = () => [...container.querySelectorAll('.qualifying-view-modes')];
    assert.equal(controls().length, 2);
    for (const control of controls()) assert.deepEqual([...control.querySelectorAll('button')].map((button) => button.textContent), ["STANDARD", "TIMING"]);
    await act(async () => controls()[0].querySelectorAll('button')[1].click());
    for (const control of controls()) assert.equal(control.querySelectorAll('button')[1].getAttribute('aria-pressed'), "true");
    assert.equal(container.querySelectorAll('[aria-label="Qualifying Timing"]').length, 2);
    assert.equal(JSON.parse(window.localStorage.getItem("slipstream.device-preferences.v1")).qualifyingTowerView, "timing");
    await act(async () => root.render(createElement(QualifyingPreferenceHarness, { ...props, analytics: qualifyingAnalytics("Q3") })));
    assert.equal(container.querySelectorAll('[aria-label="Qualifying Timing"]').length, 2);
    assert.equal(JSON.parse(window.localStorage.getItem("slipstream.device-preferences.v1")).qualifyingTowerView, "timing");
    await act(async () => controls()[1].querySelectorAll('button')[0].click());
    assert.equal(container.querySelectorAll('[aria-label="Qualifying Standard"]').length, 2);
  } finally {
    await act(async () => root.unmount());
  }
});

test("Qualifying preference reloads separately from Race and rejects Strategy", async () => {
  const key = "slipstream.device-preferences.v1";
  const container = document.getElementById("test-root");
  const props = { state: { ...EMPTY_RACE_STATE, drivers: { "1": driver } }, analytics: qualifyingAnalytics(), replayAvailable: true, sectorTimingAvailable: true, positionMode: "unavailable", viewingMode: "live", onSelectDriver() {} };
  for (const [saved, expected] of [["timing", "Timing"], ["strategy", "Standard"], [null, "Standard"]]) {
    window.localStorage.setItem(key, JSON.stringify({ towerView: "strategy", qualifyingTowerView: saved }));
    const root = createRoot(container);
    try {
      await act(async () => root.render(createElement(QualifyingPreferenceHarness, props)));
      assert.equal(container.querySelectorAll(`[aria-label="Qualifying ${expected}"]`).length, 2);
      assert.equal(JSON.parse(window.localStorage.getItem(key)).towerView, "strategy");
    } finally {
      await act(async () => root.unmount());
    }
  }
  window.localStorage.removeItem(key);
});
