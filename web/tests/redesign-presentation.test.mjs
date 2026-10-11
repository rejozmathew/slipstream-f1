import assert from "node:assert/strict";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { act, createElement, useRef } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<div id='root'></div>", { url: "http://localhost" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.HTMLElement = dom.window.HTMLElement;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
const { createRoot } = await import("react-dom/client");
const server = await createServer({ configLoader: "runner", cacheDir: "../.codex-tmp/vite-redesign-tests", root: fileURLToPath(new URL("..", import.meta.url)), server: { middlewareMode: true, hmr: false }, appType: "custom" });
after(async () => { await server.close(); dom.window.close(); });
const { fitTowerColumns, fittedTowerRowHeight } = await server.ssrLoadModule("/components/timing/towerColumns.ts");
const { PhoneTimingTower } = await server.ssrLoadModule("/components/timing/PhoneTimingTower.tsx");
const { TVModeView } = await server.ssrLoadModule("/views/TVModeView.tsx");
const { EMPTY_RACE_STATE } = await server.ssrLoadModule("/domain/protocol.ts");
const { DEFAULT_TV_PREFERENCES, useProductPreferences } = await server.ssrLoadModule("/hooks/useProductPreferences.ts");
const { isStandaloneTVRoute } = await server.ssrLoadModule("/domain/tvRoute.ts");
const { TVSessionPicker } = await server.ssrLoadModule("/views/TVSessionPicker.tsx");
const { freshRowCues, rowMotionTiming, translationY } = await server.ssrLoadModule("/domain/towerMotion.ts");
const { useTowerMotion } = await server.ssrLoadModule("/hooks/useTowerMotion.ts");
const { TowerRowEffects } = await server.ssrLoadModule("/components/timing/TowerRowEffects.tsx");
const { TimingTower } = await server.ssrLoadModule("/components/timing/TimingTower.tsx");
const { RailTransition } = await server.ssrLoadModule("/components/shared/RailTransition.tsx");
const render = (component, props) => renderToStaticMarkup(createElement(component, props));
const driver = { number: "1", code: "ONE", name: "Driver One", team: "Team One", position: 1, lap: 8, compound: "MEDIUM", tyre_age: 6, stint_laps: 6, pit_count: 1, gap_to_leader: null, interval_to_ahead: null, last_lap: "1:23.400", best_lap: "1:22.900", source_condition: "RUNNING", status: "RUNNING", activity: "ON_TRACK", classification: null, availability: {}, track_position: null, x: null, y: null };

test("narrow towers drop optional columns before reducing the 140px driver identity", () => {
  const headers = ["P", "DRIVER / TEAM", "GAP", "INT", "TYRE", "S1", "S2", "S3", "LAST", "BEST"];
  for (const width of [340, 400, 512, 620, 900]) {
    const fit = fitTowerColumns(headers, width);
    assert.match(fit.template, /minmax\(140px, 1fr\)/);
    assert.ok(!fit.hidden.includes(0) && !fit.hidden.includes(1));
    assert.ok(!fit.hidden.includes(2) && !fit.hidden.includes(4));
    assert.ok(fit.minimumWidth <= width || fit.hidden.length === 6);
  }
  const full = fitTowerColumns(headers, 340, true);
  assert.deepEqual(full.hidden, []);
  assert.ok(full.minimumWidth > 340, "full detail scrolls within the timing panel");
});

test("phone timing preserves every driver and source status without deriving missing intervals", () => {
  const drivers = Array.from({ length: 22 }, (_, index) => ({ ...driver, number: String(index + 1), code: `D${index + 1}`, position: index + 1, interval_to_ahead: index === 1 ? "+0.870" : null }));
  drivers[3] = { ...drivers[3], source_condition: "STOPPED", interval_to_ahead: "+99.999" };
  drivers[4] = { ...drivers[4], classification: "DNF", interval_to_ahead: "+88.888" };
  const html = render(PhoneTimingTower, { drivers, variant: "race", intervalsAvailable: true, replayAvailable: true });
  const doc = new JSDOM(html).window.document;
  assert.equal(doc.querySelectorAll(".phone-timing-row").length, 22);
  assert.match(html, /\+0.870/);
  assert.match(html, /STOPPED/);
  assert.match(html, /DNF/);
  assert.doesNotMatch(html, /99.999|88.888|UNKNOWN|UNAVAILABLE/);
  assert.equal(doc.querySelectorAll(".phone-metric-switch button").length, 2);
  const unsupported = render(PhoneTimingTower, { drivers, variant: "race", intervalsAvailable: false, replayAvailable: true });
  assert.doesNotMatch(unsupported, />INT</);
});

test("phone Qualifying respects active scoped best and never substitutes an earlier best lap", () => {
  const html = render(PhoneTimingTower, { drivers: [driver], variant: "qualifying", analytics: { qualifying: { drivers: { "1": { scopeBest: null, benchmarkDelta: null } } } }, replayAvailable: true });
  assert.doesNotMatch(html, /1:22.900|1:23.400/);
  assert.equal(JSDOM.fragment(html).querySelector(".phone-primary-value").textContent, "—");
});

test("TV remote commands share capability guards and close the topmost layer", async () => {
  const root = createRoot(document.getElementById("root"));
  const commands = []; let exits = 0;
  const props = { state: { ...EMPTY_RACE_STATE, drivers: { "1": driver } }, analytics: null, recommendedBattle: null, sessionLayout: "race", sessionKind: "race", replayAvailable: true, positionMode: "unavailable", viewingMode: "live", sectorTimingAvailable: false, preferences: DEFAULT_TV_PREFERENCES, onPreferencesChange() {}, onExit() { exits += 1; }, controls: createElement("input", { "aria-label": "Exact delay" }), onCommand(command) { commands.push(command); return true; }, canCommand: () => true, isPlaying: true, delaySeconds: 30 };
  const key = async (value, target = window) => act(() => target.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: value, bubbles: true, cancelable: true })));
  try {
    await act(() => root.render(createElement(TVModeView, props)));
    assert.equal(document.querySelector('.tv-toolbar'), null, "controls start hidden as in the TV reference");
    await key("ArrowLeft");
    assert.deepEqual(commands.at(-1), { type: "delay", seconds: 35 });
    await key("MediaPlayPause");
    assert.deepEqual(commands.at(-1), { type: "pause" });
    await act(() => document.querySelector(".tv-toolbar-sync").click());
    const input = document.querySelector('[aria-label="Custom live delay M:SS"]');
    const count = commands.length;
    await key("ArrowRight", input);
    assert.equal(commands.length, count, "editing a control cannot nudge the viewer");
    await key("Escape", input);
    assert.equal(document.querySelector('[role="dialog"]'), null);
    assert.equal(exits, 0);
    await key("Escape");
    assert.equal(exits, 0);
    await key("Escape");
    assert.equal(exits, 1);
    await act(() => root.render(createElement(TVModeView, { ...props, canCommand: () => false })));
    await key("MediaPlayPause");
    assert.equal(commands.length, count, "remote input respects the same denied command guard");
  } finally { await act(() => root.unmount()); }
});

test("non-race TV exposes the authored cut-line or spread and timing views without Race strategy", () => {
  for (const layout of ["practice", "qualifying"]) {
    const html = render(TVModeView, { state: { ...EMPTY_RACE_STATE, drivers: { "1": driver } }, analytics: null, recommendedBattle: null, sessionLayout: layout, sessionKind: layout, replayAvailable: true, positionMode: "unavailable", viewingMode: "replay", sectorTimingAvailable: false, preferences: DEFAULT_TV_PREFERENCES, onPreferencesChange() {}, onExit() {} });
    const doc = new JSDOM(html).window.document;
    assert.deepEqual([...doc.querySelectorAll(".tv-feature-heading button")].map((button) => button.textContent), [layout === "qualifying" ? "1CUT LINE" : "1SPREAD", "TTIMING", "AAUTO"]);
  }
});


test("standalone TV routes launch a self-contained TV entry", () => {
  for (const [path, query] of [["/tv", ""], ["/tv/", ""], ["/tv.html", "?app=1"], ["/", "?app=1"]]) assert.equal(isStandaloneTVRoute(path, query), true);
  for (const [path, query] of [["/", ""], ["/tv-news", ""], ["/", "?app=0"]]) assert.equal(isStandaloneTVRoute(path, query), false);
});

test("TV session browsing preserves the current viewer until an explicit watch or download selection", async () => {
  const root = createRoot(document.getElementById("root"));
  const watched = []; const selected = [];
  const catalogSession = { sessionKey: "race", year: 2025, meetingKey: "meeting", meetingName: "Test Grand Prix", sessionName: "Race", dateStart: "2025-08-31T13:00:00Z", available: true, liveAvailable: false, downloadable: true, circuit: "Test Circuit" };
  const catalog = { sessions: [catalogSession, { ...catalogSession, sessionKey: "practice", sessionName: "Practice", available: false }], downloadsEnabled: true };
  const props = { catalog, selectedKey: "race", viewingMode: "replay", preferences: DEFAULT_TV_PREFERENCES, error: null, downloadState: "idle", downloadError: null, onWatch: (...args) => watched.push(args), onSelect: (key) => selected.push(key), onDownload() {} };
  try {
    await act(() => root.render(createElement(TVSessionPicker, props)));
    assert.equal(document.activeElement.textContent, "RESUME REPLAY · Race");
    await act(() => document.querySelector(".tv-resume").click());
    assert.deepEqual(watched, [["race", "replay"]]);
    await act(() => [...document.querySelectorAll(".tv-session-list button")].find((button) => button.textContent.includes("Practice")).click());
    assert.deepEqual(selected, [], "browsing another session cannot reset the current viewer");
    assert.equal(document.querySelector(".tv-session-preview h2").textContent, "Practice");
    const prepare = [...document.querySelectorAll(".tv-session-actions button")].find((button) => button.textContent.includes("SELECT REPLAY"));
    assert.ok(prepare);
    await act(() => prepare.click());
    assert.deepEqual(selected, ["practice"]);
    assert.equal(document.querySelectorAll(".desktop-product-nav").length, 0);
    const buttons = [...document.querySelectorAll("button:not(:disabled)")];
    buttons.forEach((button, index) => { button.getBoundingClientRect = () => ({ left: index * 100, top: 0, width: 90, height: 44 }); });
    buttons[0].focus();
    await act(() => buttons[0].dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, cancelable: true })));
    assert.equal(document.activeElement, buttons[1]);
    await act(() => buttons[1].dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "BrowserBack", bubbles: true, cancelable: true })));
    assert.equal(document.activeElement, buttons[0], "Back at the TV entry stays in the session list");
  } finally { await act(() => root.unmount()); }
});

const motionEvent = (kind, sequence, extra = {}) => ({ id: `${kind}-${sequence}`, sessionKey: "race", kind, occurredAt: "2025-08-31T13:00:00Z", availableAt: "2025-08-31T13:00:05Z", availableSequence: sequence, driverNumbers: ["1", "2"], cause: "ON_TRACK", state: "confirmed", data: {}, ...extra });
const motionStory = (sequence, events) => ({ sequence, asOf: "2025-08-31T13:00:20Z", events });

test("motion cause colour requires fresh available server evidence and never turns an order change into a pass", () => {
  assert.equal(freshRowCues(motionStory(105, [motionEvent("ORDER_CHANGE", 105)]), 100, "GREEN", 1).size, 0);
  for (const event of [motionEvent("PASS", 106), motionEvent("PASS", 100), motionEvent("PASS", 105, { state: "provisional" }), motionEvent("PASS", 105, { cause: null }), motionEvent("PASS", 105, { availableAt: "2025-08-31T13:00:30Z" })]) assert.equal(freshRowCues(motionStory(105, [event]), 100, "GREEN", 1).size, 0);
  const story = motionStory(105, [motionEvent("PASS", 105)]);
  assert.equal(freshRowCues(story, 100, "YELLOW", 1).size, 0);
  assert.equal(freshRowCues(story, 100, "GREEN", 30).size, 0);
  assert.equal(freshRowCues(story, 100, "GREEN", 1).get("1").cause, "pass");
  assert.equal(freshRowCues(story, 100, "GREEN", 1).get("2").cause, "passed");
  const best = motionStory(106, [motionEvent("LAP_IMPROVEMENT", 106, { driverNumbers: ["1"], data: { sessionBest: true } })]);
  assert.equal(freshRowCues(best, 105, "GREEN", 1).get("1").label, "SESSION BEST");
  assert.ok(Math.abs(rowMotionTiming("pass", 1, "tv", 5).duration - 520 * 1.35 * .6) < 1e-9);
});

// Test-only fixture harness; the production hook owns its TypeScript input contract.
// eslint-disable-next-line react/prop-types
function MotionHarness({ story, generation = 0, reduced = false, speed = 1, order = ["1", "2"], playing = true }) {
  const table = useRef(null);
  useTowerMotion(table, order, story);
  return createElement("div", { className: "app-shell", "data-navigation-generation": generation, "data-reduced-motion": reduced, "data-playback-speed": speed, "data-viewer-playing": playing, "data-track-status": "GREEN", "data-session-key": "race" }, createElement("div", { ref: table, "data-motion-variant": "race" }, order.map((number) => createElement("button", { key: number, "data-driver-number": number }, createElement("strong", null, number), createElement("span", { className: "driver-cell" }, createElement("em", null, "Team")), createElement("span", { className: "tower-time" }, "1:23.000"), createElement(TowerRowEffects)))));
}

test("row cues are silent on initial history and navigation, static in reduced motion, and absent at30x", async () => {
  const root = createRoot(document.getElementById("root"));
  const proto = dom.window.HTMLElement.prototype;
  const originalBounds = proto.getBoundingClientRect; const originalAnimate = proto.animate;
  const animations = [];
  proto.getBoundingClientRect = () => ({ left: 0, top: 0, width: 400, height: 100 });
  proto.animate = function () { const animation = { playState: "running", cancel() { this.playState = "idle"; } }; animations.push(animation); return animation; };
  const row = () => document.querySelector('[data-driver-number="1"]');
  try {
    await act(() => root.render(createElement(MotionHarness, {})));
    await act(() => root.render(createElement(MotionHarness, { story: motionStory(105, [motionEvent("PASS", 105)]) })));
    assert.equal(row().dataset.motionCause, undefined, "first story snapshot is history");
    await act(() => root.render(createElement(MotionHarness, { story: motionStory(106, [motionEvent("PASS", 106)]) })));
    assert.equal(row().dataset.motionCause, "pass");
    await act(() => root.render(createElement(MotionHarness, { story: motionStory(106, [motionEvent("PASS", 106)]), speed: 30 })));
    assert.equal(row().dataset.motionCause, undefined);
    assert.ok(animations.every((animation) => animation.playState === "idle"));
    const count = animations.length;
    await act(() => root.render(createElement(MotionHarness, { story: motionStory(107, [motionEvent("LAP_IMPROVEMENT", 107, { data: { sessionBest: true } })]), reduced: true })));
    assert.equal(row().dataset.motionCause, "best");
    assert.equal(row().querySelector("em").textContent, "Team", "cause decoration does not replace driver identity");
    assert.equal(row().querySelector(".tower-time").dataset.motionFlash, "best");
    assert.equal(animations.length, count, "reduced motion retains static cause without animation");
    await act(() => root.render(createElement(MotionHarness, { story: motionStory(108, [motionEvent("PASS", 108)]), generation: 1, reduced: true })));
    assert.equal(row().dataset.motionCause, undefined, "navigation clears old labels without replaying alerts");
  } finally { await act(() => root.unmount()); proto.getBoundingClientRect = originalBounds; proto.animate = originalAnimate; }
});

test("rail transition generations cancel old status effects without altering the displayed fact", async () => {
  const root = createRoot(document.getElementById("root"));
  try {
    await act(() => root.render(createElement(RailTransition, { status: "GREEN" })));
    assert.equal(document.querySelector(".rail-transition").dataset.transition, "none");
    for (const [status, transition] of [["YELLOW", "escalate"], ["VSC", "escalate"], ["VSC_ENDING", "fade"], ["SAFETY_CAR", "escalate"], ["RED_FLAG", "escalate"], ["GREEN", "fade"], ["CHEQUERED", "escalate"]]) {
      await act(() => root.render(createElement(RailTransition, { status })));
      assert.equal(document.querySelector(".rail-transition").dataset.status, status);
      assert.equal(document.querySelector(".rail-transition").dataset.transition, transition, status);
    }
    await act(() => root.render(createElement(RailTransition, { status: "RED_FLAG" })));
    const red = document.querySelector(".rail-transition");
    assert.equal(red.dataset.transition, "escalate");
    await act(() => root.render(createElement(RailTransition, { status: "GREEN", generation: 1 })));
    assert.notEqual(document.querySelector(".rail-transition"), red);
    assert.equal(document.querySelector(".rail-transition").dataset.transition, "none");
  } finally { await act(() => root.unmount()); }
});

test("empty phone timing values render an unknown dash", () => {
  const html = render(PhoneTimingTower, { drivers: [{ ...driver, position: 2, interval_to_ahead: "" }], variant: "race", intervalsAvailable: true, replayAvailable: true });
  assert.equal(JSDOM.fragment(html).querySelector(".phone-primary-value").textContent, "—");
});

test("desktop and TV share one persisted pinned pair without changing the followed driver", async () => {
  const storageKey = "slipstream.device-preferences.v1";
  const saved = window.localStorage.getItem(storageKey);
  let root; let preferences;
  function PreferencesHarness() { preferences = useProductPreferences(); return null; }
  try {
    window.localStorage.removeItem(storageKey);
    root = createRoot(document.getElementById("root"));
    await act(() => root.render(createElement(PreferencesHarness)));
    await act(() => preferences.setTV({ ...preferences.tv, selectedDriverNumber: "16" }));
    await act(() => preferences.setBattle({ mode: "pinned", pinnedPair: ["16", "81"] }));
    assert.deepEqual(preferences.tv.pinnedBattle, ["16", "81"]);
    assert.equal(preferences.tv.battleMode, "pinned");
    await act(() => preferences.setTV({ ...preferences.tv, pinnedBattle: ["16", "4"] }));
    assert.deepEqual(preferences.battle.pinnedPair, ["16", "4"]);
    await act(() => root.unmount());
    root = createRoot(document.getElementById("root"));
    await act(() => root.render(createElement(PreferencesHarness)));
    assert.deepEqual(preferences.tv.pinnedBattle, ["16", "4"]);
    assert.deepEqual(preferences.battle.pinnedPair, ["16", "4"]);
    assert.equal(preferences.tv.selectedDriverNumber, "16");
  } finally { if (root) await act(() => root.unmount()); if (saved == null) window.localStorage.removeItem(storageKey); else window.localStorage.setItem(storageKey, saved); }
});

test("TV row measurements fit all22 drivers and provide separate scaled value columns", () => {
  const height = fittedTowerRowHeight(928, 28, 22, true);
  assert.ok(height * 22 + 28 <= 928);
  assert.ok(height > 40 && height < 41);
  const fit = fitTowerColumns(["P", "DRIVER / TEAM", "GAP", "INT", "TYRE", "PIT"], 739, false, 1.45);
  assert.deepEqual(fit.hidden, []);
  assert.ok(fit.minimumWidth < 739);
  assert.ok(fit.template.includes("113.1px 113.1px"), "GAP and INT each reserve room for TV type and padding");
  assert.equal(fittedTowerRowHeight(928, 28, 22), 38, "desktop density remains bounded separately");
});

test("TV remote separates field navigation from editing and keeps an open panel's toolbar mounted", async () => {
  const root = createRoot(document.getElementById("root"));
  const originalTimeout = globalThis.setTimeout;
  const initialTimers = [];
  globalThis.setTimeout = (callback, delay, ...args) => { if (delay === 6000) initialTimers.push(callback); return originalTimeout(callback, delay, ...args); };
  const props = { state: { ...EMPTY_RACE_STATE, drivers: { "1": driver } }, analytics: null, recommendedBattle: null, sessionLayout: "race", sessionKind: "race", replayAvailable: true, positionMode: "unavailable", viewingMode: "replay", sectorTimingAvailable: false, preferences: DEFAULT_TV_PREFERENCES, onPreferencesChange() {}, onExit() {} };
  const key = async (value, target) => act(() => target.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: value, bubbles: true, cancelable: true })));
  try {
    await act(() => root.render(createElement(TVModeView, props)));
    await key("ArrowUp", window);
    const settings = [...document.querySelectorAll(".tv-toolbar button")].find((button) => button.textContent === "SETTINGS");
    settings.focus();
    await act(() => settings.click());
    await act(() => initialTimers[0]());
    assert.ok(document.querySelector(".tv-toolbar"), "initial timeout cannot remove an open panel's return-focus target");
    const targets = [...document.querySelectorAll(".tv-overlay button, .tv-overlay select, .tv-overlay input")];
    targets.forEach((element, index) => { element.getBoundingClientRect = () => ({ left: 0, top: index * 50, width: 150, height: 44 }); });
    const field = document.querySelector(".tv-overlay select");
    const next = targets[targets.indexOf(field) + 1];
    let nativeArrows = 0;
    field.addEventListener("keydown", (event) => { if (event.key.startsWith("Arrow")) nativeArrows += 1; });
    field.focus();
    await key("ArrowDown", field);
    assert.equal(document.activeElement, next);
    assert.equal(nativeArrows, 0, "navigation capture prevents native value changes");
    await key("ArrowUp", next);
    assert.equal(document.activeElement, field);
    await key("Enter", field);
    assert.equal(document.querySelector(".tv-redesign").dataset.editingControl, "true");
    await key("ArrowDown", field);
    assert.equal(document.activeElement, field);
    assert.equal(nativeArrows, 1, "editing delegates arrows to the native field");
    await key("BrowserBack", field);
    assert.ok(document.querySelector('[role="dialog"]'));
    assert.equal(document.querySelector(".tv-redesign").dataset.editingControl, "false");
    await key("ArrowDown", field);
    assert.equal(document.activeElement, next);
    await key("Escape", next);
    assert.equal(document.querySelector('[role="dialog"]'), null);
    assert.equal(document.activeElement, settings);
  } finally { await act(() => root.unmount()); globalThis.setTimeout = originalTimeout; }
});

test("phone qualifying rows retain the team alongside the source activity badge", () => {
  const html = render(PhoneTimingTower, { drivers: [{ ...driver, activity: "IN_PIT", source_condition: "RUNNING", status: "IN_PIT" }], variant: "qualifying", replayAvailable: true });
  const doc = new JSDOM(html).window.document;
  assert.equal(doc.querySelector(".phone-identity small").textContent, "Team One");
  assert.equal(doc.querySelector(".phone-state-badge").textContent, "IN PIT");
});


test("tower matrix parsing preserves 2D and 3D in-flight translation without NaN", () => {
  assert.equal(translationY("matrix(1, 0, 0, 1, 0, -16.5)"), -16.5);
  assert.equal(translationY("matrix3d(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 22.25, 0, 1)"), 22.25);
  assert.equal(translationY("none"), 0);
  assert.equal(translationY("matrix(1, 0, 0, 1, 0, invalid)"), 0);
});

test("timing updates preserve each active move and retarget from its visible position", async () => {
  const root = createRoot(document.getElementById("root"));
  const proto = dom.window.HTMLElement.prototype;
  const originalBounds = proto.getBoundingClientRect; const originalAnimate = proto.animate;
  const originalTop = Object.getOwnPropertyDescriptor(proto, "offsetTop");
  const originalHeight = Object.getOwnPropertyDescriptor(proto, "offsetHeight");
  const originalComputed = window.getComputedStyle;
  const transforms = new Map(); const animations = [];
  proto.getBoundingClientRect = () => ({ left: 0, top: 0, width: 400, height: 128 });
  Object.defineProperty(proto, "offsetTop", { configurable: true, get() { return this.dataset.driverNumber ? [...this.parentElement.children].indexOf(this) * 32 : 0; } });
  Object.defineProperty(proto, "offsetHeight", { configurable: true, get() { return 32; } });
  window.getComputedStyle = (element) => ({ transform: transforms.get(element.dataset.driverNumber) ?? "none" });
  proto.animate = function (frames, options) {
    const animation = { target: this, frames, options, playState: "running", cancel() { this.playState = "idle"; } };
    animations.push(animation); return animation;
  };
  const travel = (number) => animations.filter((animation) => animation.target.dataset.driverNumber === number && animation.frames[0].transform);
  try {
    await act(() => root.render(createElement(MotionHarness, { order: ["1", "2", "3", "4"], story: motionStory(100, []) })));
    await act(() => root.render(createElement(MotionHarness, { order: ["2", "1", "3", "4"], story: motionStory(101, []) })));
    assert.equal(travel("1")[0].frames[0].transform, "translateY(-32px)");
    assert.equal(travel("2")[0].frames[0].transform, "translateY(32px)");
    assert.equal(travel("1")[0].options.duration, 700, "unconfirmed order changes use the reference neutral profile");
    const first = travel("1")[0]; const other = travel("2")[0];
    await act(() => root.render(createElement(MotionHarness, { order: ["2", "1", "3", "4"], story: motionStory(102, []) })));
    assert.equal(travel("1").length, 1, "ordinary timing packets do not restart travel");
    await act(() => root.render(createElement(MotionHarness, { order: ["2", "1", "4", "3"], story: motionStory(103, []) })));
    assert.equal(first.playState, "running", "another driver's reorder must not cancel this move");
    assert.equal(other.playState, "running");
    transforms.set("1", "matrix(1, 0, 0, 1, 0, -16)");
    await act(() => root.render(createElement(MotionHarness, { order: ["2", "4", "1", "3"], story: motionStory(104, []) })));
    assert.equal(first.playState, "idle");
    assert.equal(travel("1").at(-1).frames[0].transform, "translateY(-48px)", "rebase includes the previous visual remainder");
    assert.equal(other.playState, "running", "retargeting one driver leaves unrelated travel intact");
    const moves = animations.filter((animation) => animation.frames[0].transform);
    await act(() => root.render(createElement(MotionHarness, { order: ["1", "2", "3", "4"], story: motionStory(110, []), generation: 1 })));
    assert.ok(moves.every((animation) => animation.playState === "idle"));
    assert.equal(animations.filter((animation) => animation.frames[0].transform).length, moves.length, "a jump snaps instead of replaying overtakes");
  } finally {
    await act(() => root.unmount()); proto.getBoundingClientRect = originalBounds; proto.animate = originalAnimate; window.getComputedStyle = originalComputed;
    Object.defineProperty(proto, "offsetTop", originalTop); Object.defineProperty(proto, "offsetHeight", originalHeight);
  }
});

test("late confirmed passes add reference emphasis without replaying the earlier row change", async () => {
  const root = createRoot(document.getElementById("root"));
  const proto = dom.window.HTMLElement.prototype;
  const originalBounds = proto.getBoundingClientRect; const originalAnimate = proto.animate;
  const animations = [];
  proto.getBoundingClientRect = () => ({ left: 0, top: 0, width: 400, height: 100 });
  proto.animate = function (frames, options) { const animation = { target: this, frames, options, playState: "running", cancel() { this.playState = "idle"; } }; animations.push(animation); return animation; };
  try {
    await act(() => root.render(createElement(MotionHarness, { story: motionStory(100, []), order: ["2", "1"] })));
    await act(() => root.render(createElement(MotionHarness, { story: undefined, order: ["2", "1"] })));
    await act(() => root.render(createElement(MotionHarness, { story: motionStory(105, [motionEvent("PASS", 105)]), order: ["2", "1"] })));
    const row = document.querySelector('[data-driver-number="1"]');
    assert.equal(row.querySelector(".tower-motion-delta").textContent, "▲1");
    assert.equal(row.querySelector(".driver-cell em").textContent, "Team");
    assert.ok(animations.some((animation) => animation.target.className === "tower-motion-wash" && animation.options.duration === 2600));
    assert.ok(animations.some((animation) => animation.target.tagName === "STRONG" && animation.frames[0].transform === "scale(1.6)"));
    assert.equal(animations.filter((animation) => animation.target.dataset.driverNumber && animation.frames[0].transform).length, 0, "late cause emphasis must not replay a historical reorder");
  } finally { await act(() => root.unmount()); proto.getBoundingClientRect = originalBounds; proto.animate = originalAnimate; }
});

test("compact TV tower keeps the reference INT/GAP order and tyre age within TYRE", () => {
  const fragment = JSDOM.fragment(render(TimingTower, { drivers: [{ ...driver, tyre_age: 11 }], variant: "race", tvScale: 1, compact: true, desktopRaceColumns: true, intervalsAvailable: true, replayAvailable: true }));
  assert.deepEqual([...fragment.querySelectorAll(".timing-header > span")].map((cell) => cell.textContent), ["P", "DRIVER / TEAM", "INT", "GAP", "TYRE", "PIT"]);
  assert.equal(fragment.querySelector(".tv-tower-tyre small").textContent, "11L");
  assert.equal(fragment.querySelectorAll(".tower-motion-effects[aria-hidden=true]").length, 1);
  assert.match(fragment.querySelector(".timing-table").getAttribute("style"), /98\.6px/);
});
