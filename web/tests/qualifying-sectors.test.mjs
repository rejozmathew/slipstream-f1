import assert from "node:assert/strict";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
const server = await createServer({ configLoader: "runner", cacheDir: "../.codex-tmp/vite-sector-tests", root: fileURLToPath(new URL("..", import.meta.url)), server: { middlewareMode: true, hmr: false }, appType: "custom" });
after(() => server.close());
const { SectorValue } = await server.ssrLoadModule("/components/timing/SectorValue.tsx");
const { sessionStatusLabel } = await server.ssrLoadModule("/domain/sessionStatus.ts");
const { SessionStrip } = await server.ssrLoadModule("/components/shell/SessionStrip.tsx");
const { EMPTY_RACE_STATE } = await server.ssrLoadModule("/domain/protocol.ts");
const { describeStory } = await server.ssrLoadModule("/components/story/presentation.ts");
const { TimingTower } = await server.ssrLoadModule("/components/timing/TimingTower.tsx");
const { PhoneTimingTower } = await server.ssrLoadModule("/components/timing/PhoneTimingTower.tsx");
const { DriverFocusView } = await server.ssrLoadModule("/views/DriverFocusView.tsx");

test("tower uses best-lap sectors while Driver history preserves separately graded segments", () => {
  const driver = { number: "1", code: "D1", position: 1, availability: {}, source_condition: "RUNNING" };
  const attempt = { attempt: 1, phase: "SQ1", lap: 4, lapTime: 75, sector1: 24.111, sector2: 25.222, sector3: 25.667,
    sector1Status: "SESSION_BEST", sector2Status: "PERSONAL_BEST", sector3Status: "SLOWER", classification: "TIMED", validity: "UNKNOWN", tyreUsage: "UNKNOWN" };
  const analytics = { sessionKind: "sprint_qualifying", drivers: {}, qualifying: { phase: "SQ2", cutLine: { status: "UNKNOWN" }, drivers: {
    1: { scopeBest: "1:15.000", scopeBestLap: attempt, scopeLatestLap: { ...attempt, sector1: 99.999 }, attempts: [attempt, { ...attempt, attempt: 2, phase: "SQ2", lap: 8, sector1: 23.333 }, { ...attempt, attempt: 3, phase: "SQ2", lap: 9, sector1: 22.444 }], segmentResults: [75, 74, null] },
  } } };
  const tower = renderToStaticMarkup(createElement(TimingTower, { drivers: [driver], variant: "qualifying", mode: "timing", sectorTimingAvailable: true, analytics }));
  assert.match(tower, /24\.111/);
  assert.doesNotMatch(tower, /99\.999/);
  assert.match(tower, /best completed lap/);
  const history = renderToStaticMarkup(createElement(DriverFocusView, {
    state: { ...EMPTY_RACE_STATE, drivers: { 1: driver } }, analytics, sessionLayout: "qualifying", driverNumber: "1", history: null,
    positionMode: "unavailable", viewingMode: "replay", onChangeDriver() {}, onBack() {},
  }));
  assert.match(history, /aria-label="SQ1 lap history"/);
  assert.match(history, /aria-label="SQ2 lap history"/);
  assert.match(history, /within each segment at the viewing time/);
  for (const grade of ["session_best", "personal_best", "slower"]) assert.match(history, new RegExp(`sector-value sector-${grade}`));
  assert.match(history, /23\.333/);
  assert.match(history, /LATEST FIRST/);
  assert.match(history, /SESSION LAP 4/);
  assert.match(history, /Only recorded laps are shown; gaps can occur/);
  assert.ok(history.indexOf('aria-label="SQ2 lap history"') < history.indexOf('aria-label="SQ1 lap history"'));
  assert.ok(history.indexOf('SESSION LAP 9') < history.indexOf('SESSION LAP 8'));
  assert.deepEqual(analytics.qualifying.drivers[1].attempts.map((lap) => lap.attempt), [1, 2, 3], "presentation must not mutate source history");
  Object.assign(analytics.qualifying.drivers[1].attempts[2], { lap: null, lapNumberStatus: "UNCONFIRMED" });
  const unconfirmed = renderToStaticMarkup(createElement(DriverFocusView, {
    state: { ...EMPTY_RACE_STATE, drivers: { 1: driver } }, analytics, sessionLayout: "qualifying", driverNumber: "1", history: null,
    positionMode: "unavailable", viewingMode: "replay", onChangeDriver() {}, onBack() {},
  }));
  assert.match(unconfirmed, /LAP NUMBER UNCONFIRMED/);
  assert.doesNotMatch(unconfirmed, /SESSION LAP 9|SESSION LAP null/);
  analytics.qualifying.drivers[1].scopeBestLap = null;
  const missing = renderToStaticMarkup(createElement(TimingTower, { drivers: [driver], variant: "qualifying", mode: "timing", sectorTimingAvailable: true, analytics }));
  assert.doesNotMatch(missing, /24\.111|99\.999/);
});

test("sector cells render server grades with accessible meanings and neutral fallback", () => {
  for (const [status, label] of [["SESSION_BEST", "Fastest observed"], ["PERSONAL_BEST", "best observed"], ["SLOWER", "Slower than"], ["UNKNOWN", "comparison unavailable"]]) {
    const html = renderToStaticMarkup(createElement(SectorValue, { value: 25.123, status }));
    assert.match(html, new RegExp(`sector-${status.toLowerCase()}`));
    assert.match(html, new RegExp(label));
    assert.match(html, /25\.123/);
  }
  const missing = renderToStaticMarkup(createElement(SectorValue, { value: null, status: "SESSION_BEST" }));
  assert.match(missing, /sector-unknown/);
  assert.doesNotMatch(missing, /sector-session_best/);
});

test("qualifying flags name the segment without masking red flags or persisting after restart", () => {
  const session = { ...EMPTY_RACE_STATE.session, layout_family: "qualifying", display_status: "CHEQUERED" };
  for (const phase of ["Q1", "Q2", "Q3", "SQ1", "SQ2", "SQ3"]) {
    assert.equal(sessionStatusLabel({ ...session, qualifying_phase: phase }), `${phase} ENDED`);
    assert.equal(sessionStatusLabel({ ...session, qualifying_phase: phase, display_status: "RED_FLAG" }), "RED FLAG");
    assert.equal(sessionStatusLabel({ ...session, qualifying_phase: phase, display_status: "GREEN" }), "GREEN");
  }
  assert.equal(sessionStatusLabel({ ...session, qualifying_phase: "UNKNOWN" }), "CHEQUERED");
  assert.equal(sessionStatusLabel({ ...session, layout_family: "race", qualifying_phase: "SQ1" }), "CHEQUERED");
  const html = renderToStaticMarkup(createElement(SessionStrip, { session: { ...session, qualifying_phase: "SQ1" }, selected: null, viewingMode: "replay", livePhase: "LIVE", liveNow: false, onGoLive() {} }));
  assert.match(html, /SQ1 ENDED/);
  assert.match(html, /data-track-status="chequered"/);
  assert.match(html, /data-status="CHEQUERED"/);
  const event = { kind: "SESSION_END", phase: "SQ1", data: {}, driverNumbers: [], title: "SQ1 flag shown", detail: "Laps finishing" };
  assert.equal(describeStory(event).tag, "SQ1 ENDED");
  assert.equal(describeStory({ ...event, kind: "FLAG", data: { flag: "CHEQUERED" } }).title, "SQ1 ended");
  assert.equal(describeStory({ ...event, phase: null, data: { settled: true } }).tag, "SESSION COMPLETE");
});

test("desktop, TV and phone fade confirmed elimination, never a provisional drop-zone position", () => {
  const drivers = [true, false, null].map((eliminated, index) => ({ number: String(index + 1), code: `D${index + 1}`, position: index + 17, qualifying_eliminated: eliminated, source_condition: "RUNNING", activity: "IN_PIT", availability: {} }));
  const qualifying = { phase: "SQ2", cutLine: { status: "AVAILABLE", advancePosition: 10 }, drivers: {
    1: { cutState: "ELIMINATED", qStatus: "OUT SQ1" },
    2: { cutState: "ELIMINATED", qStatus: null }, // Explicit current false wins over stale analytics.
    3: { cutState: "BELOW_CUT", qStatus: null },
  } };
  for (const [component, extra] of [[TimingTower, {}], [TimingTower, { compact: true, tvScale: 1 }], [PhoneTimingTower, {}]]) {
    const html = renderToStaticMarkup(createElement(component, { drivers, variant: "qualifying", replayAvailable: true, analytics: { qualifying, sessionKind: "sprint_qualifying" }, ...extra }));
    assert.equal((html.match(/qualifying-eliminated/g) ?? []).length, 1);
    assert.match(html, /OUT SQ1/);
    assert.doesNotMatch(html, /disabled/);
  }
});
