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
const { SessionStrip } = await server.ssrLoadModule("/components/shell/SessionStrip.tsx");
const { SessionProgress } = await server.ssrLoadModule("/components/shared/SessionProgress.tsx");
const { TimingTower } = await server.ssrLoadModule("/components/timing/TimingTower.tsx");
const { DriverFocusView } = await server.ssrLoadModule("/views/DriverFocusView.tsx");
const render = (component, props) => renderToStaticMarkup(createElement(component, props));
const driver = {
  number: "1", code: "ONE", name: "Driver One", team: "Team", position: 3, lap: 12,
  compound: "SOFT", tyre_age: 5, stint_laps: 5, pit_count: 2,
  gap_to_leader: "+0.685", last_lap: "1:24.123", best_lap: "1:23.456",
  best_lap_delta_to_ahead: "+0.249",
  source_condition: "RUNNING", status: "RUNNING", activity: "ON_TRACK",
  classification: null, availability: {}, track_position: null, x: null, y: null,
};

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
    await act(() => button("2m").click());
    assert.deepEqual(commands.at(-1), { type: "delay", seconds: 120 });
    assert.equal(container.querySelector("[aria-live]").textContent, "LIVE");
    await update(120);
    assert.equal(container.querySelector("[aria-live]").textContent, "DELAY 2:00");
    await submit("2:17");
    assert.deepEqual(commands.at(-1), { type: "delay", seconds: 137 });
    await update(30);
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
    assert.equal(container.querySelector("[aria-live]").textContent, "LIVE");
  } finally {
    await act(() => root.unmount());
  }
});
