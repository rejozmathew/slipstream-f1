import assert from "node:assert/strict";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { act, createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { JSDOM } from "jsdom";
import { createServer } from "vite";
import { canViewerCommand } from "../domain/viewerCommands.mjs";

const dom = new JSDOM("<div id='viewer'></div>", { url: "http://localhost" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import("react-dom/client");
const server = await createServer({ configLoader: "runner", cacheDir: "../.codex-tmp/vite-viewer-tests", root: fileURLToPath(new URL("..", import.meta.url)), server: { middlewareMode: true, hmr: false, ws: false }, appType: "custom" });
after(async () => { await server.close(); dom.window.close(); });
const { slipstreamApi } = await server.ssrLoadModule("/api/client.ts");
const { useSlipstreamSession } = await server.ssrLoadModule("/hooks/useSlipstreamSession.ts");
const { EMPTY_RACE_STATE } = await server.ssrLoadModule("/domain/protocol.ts");
const { LiveControls } = await server.ssrLoadModule("/components/shell/LiveControls.tsx");
const { currentPairGap } = await server.ssrLoadModule("/domain/battle.ts");
const { battleGapPresentation } = await server.ssrLoadModule("/domain/correctness.mjs");
const { StoryFeed } = await server.ssrLoadModule("/components/story/StoryFeed.tsx");
const { StoryMoments } = await server.ssrLoadModule("/components/story/StoryMoments.tsx");

test("every live input is constrained to fixed-speed pause/resume, delay and Go Live", () => {
  for (const command of [{ type: "seek", seq: 0 }, { type: "seek_relative", seconds: 10 }, { type: "step" }, { type: "play", speed: 2 }, { type: "delay", seconds: 301 }]) {
    assert.equal(canViewerCommand("live", true, false, command), false);
  }
  for (const command of [{ type: "pause" }, { type: "play", speed: 1 }, { type: "reset" }, { type: "delay", seconds: 300 }]) {
    assert.equal(canViewerCommand("live", true, false, command), true);
    assert.equal(canViewerCommand("live", false, false, command), false);
  }
  assert.equal(canViewerCommand("replay", true, false, { type: "play", speed: 1 }), false);
  assert.equal(canViewerCommand("replay", true, true, { type: "play", speed: 0.5 }), true);
  assert.equal(canViewerCommand("replay", true, true, { type: "play", speed: 120 }), true);
  assert.equal(canViewerCommand("replay", true, true, { type: "play", speed: 0.1 }), false);
});

test("live controls expose requested/effective delay and the auto-resume announcement", () => {
  const html = renderToStaticMarkup(createElement(LiveControls, {
    phase: "LIVE", delaySeconds: 192, requestedDelaySeconds: 300, isPlaying: false,
    notice: "Playback resumed: the 5:00 live delay limit was reached.", commandAvailable: true, onCommand: () => true,
  }));
  assert.match(html, /Asked 5:00 · buffer holds 3:12/);
  assert.match(html, /RESUME/);
  assert.match(html, /role="status"/);
  assert.match(html, /5:00 live delay limit/);
  assert.match(html, /GO LIVE/);
});

test("pinned pair gaps never fall back to browser leader-gap arithmetic", () => {
  const left = { number: "1", position: 1, gap_to_leader: "LEADER" };
  const right = { number: "3", position: 3, gap_to_leader: "+9.5" };
  assert.equal(currentPairGap(null, left, right), null);
  assert.equal(currentPairGap({ battle: { candidates: [] } }, left, right), null);
  const comparison = { aheadDriverNumber: "1", behindDriverNumber: "3", gapSeconds: 4.8, gapBasis: "leader_gap_difference", comparisonState: "COMPARABLE", reason: null };
  const analytics = { battle: { candidates: [], pairs: { "1:3": comparison } } };
  assert.equal(currentPairGap(analytics, left, right), 4.8);
  assert.equal(currentPairGap(analytics, right, left), 4.8);
  comparison.comparisonState = "NOT_COMPARABLE";
  comparison.reason = "The drivers are not on the same observed lap.";
  assert.equal(currentPairGap(analytics, left, right), null);
  assert.match(battleGapPresentation(comparison).note, /same observed lap/);
});

const at = (seconds) => new Date(Date.UTC(2026, 8, 5, 12, 0, seconds)).toISOString();
async function scenario(mode, check, render = () => null) {
  const originalApi = { ...slipstreamApi };
  const originalSocket = globalThis.WebSocket;
  const originalTimers = Object.fromEntries(["setTimeout", "clearTimeout", "setInterval", "clearInterval"].map((key) => [key, window[key]]));
  const timers = new Map();
  let id = 0;
  window.setTimeout = (callback, delay) => { timers.set(++id, { callback, delay }); return id; };
  window.setInterval = window.setTimeout;
  window.clearTimeout = window.clearInterval = (value) => timers.delete(value);
  const sockets = [];
  globalThis.WebSocket = class {
    static OPEN = 1;
    readyState = 1;
    sent = [];
    constructor(url) { this.url = url; sockets.push(this); }
    close() { if (this.readyState !== 3) { this.readyState = 3; this.onclose?.(); } }
    send(command) { this.sent.push(JSON.parse(command)); }
    emit(frame) { this.onmessage?.({ data: JSON.stringify(frame) }); }
  };
  slipstreamApi.catalog = async () => ({ defaultSessionKey: "A", liveSessionKey: mode === "live" ? "A" : null, sessions: [{ sessionKey: "A", available: mode === "replay", recordingVersion: "v1", liveAvailable: mode === "live" }] });
  slipstreamApi.jobs = async () => ({ jobs: [] });
  slipstreamApi.state = async () => { throw Error("Offline"); };
  slipstreamApi.analytics = async () => { throw Error("No optional analytics"); };
  window.localStorage.clear();
  window.localStorage.setItem("slipstream.selected-session.v1", "A");
  window.localStorage.setItem("slipstream.viewing-intent.v2", JSON.stringify({ mode, followLive: false }));
  let current;
  function Host() { current = useSlipstreamSession(); return render(current); }
  const root = createRoot(document.getElementById("viewer"));
  const frame = (seconds, extra = {}) => ({
    type: "state.snapshot", v: 1, seq: seconds, sessionTime: at(seconds), sourceTime: at(seconds),
    mode, playbackReady: true, playback: { playing: false },
    data: { ...EMPTY_RACE_STATE, session: { ...EMPTY_RACE_STATE.session, key: "A" } },
    metadata: { available: true, replayAvailable: true, sessionKey: "A", recordingVersion: "v1" },
    capabilities: { v: 1, source: "synthetic", capabilities: {} },
    ...(mode === "live" ? { live: { phase: "LIVE", status: "LIVE", paused: false, stale: false, delaySeconds: 0, requestedDelaySeconds: 0, navigationGeneration: 0 } } : {}),
    ...extra,
  });
  try {
    await act(async () => root.render(createElement(Host)));
    await check({ current: () => current, sockets, frame, retry: async () => { for (const timer of timers.values()) if (timer.delay === 500) await timer.callback(); } });
  } finally {
    await act(async () => root.unmount());
    Object.assign(slipstreamApi, originalApi);
    Object.assign(window, originalTimers);
    globalThis.WebSocket = originalSocket;
  }
}

test("replaying a moment preserves the original cursor, play state and speed", async () => scenario("replay", async ({ current, sockets, frame }) => {
  const socket = sockets.at(-1);
  await act(async () => socket.emit(frame(100, { playback: { playing: true } })));
  await act(async () => current().setPlaybackSpeed(30));
  const originalGeneration = current().navigationGeneration;
  await act(async () => assert.equal(current().replayMoment(at(50)), true));
  assert.deepEqual(socket.sent.slice(-2), [{ type: "seek", at: at(50) }, { type: "play", speed: 1 }]);
  assert.equal(current().hasReturnPoint, true);
  assert.ok(current().navigationGeneration > originalGeneration);
  await act(async () => socket.emit(frame(50, { playback: { playing: true } })));
  assert.equal(current().watchedUntil, at(100));
  await act(async () => current().replayMoment(at(20)));
  await act(async () => current().returnFromMoment());
  assert.deepEqual(socket.sent.slice(-2), [{ type: "seek", seq: 100, playhead: at(100) }, { type: "play", speed: 30 }]);
  assert.equal(current().playbackSpeed, 30);
  assert.equal(current().hasReturnPoint, false);
}));

test("returning to a paused point remains paused and replacement recordings reset spoilers", async () => scenario("replay", async ({ current, sockets, frame }) => {
  const socket = sockets.at(-1);
  await act(async () => socket.emit(frame(80)));
  await act(async () => current().replayMoment(at(20)));
  await act(async () => socket.emit(frame(20, { playback: { playing: true } })));
  await act(async () => current().returnFromMoment());
  assert.deepEqual(socket.sent.at(-1), { type: "seek", seq: 80, playhead: at(80) });
  await act(async () => socket.emit(frame(80)));
  assert.equal(current().isPlaying, false);
  await act(async () => socket.emit(frame(1, { metadata: { available: true, replayAvailable: true, sessionKey: "A", recordingVersion: "v2" } })));
  assert.equal(current().watchedUntil, at(1));
}));

test("a live paused cursor survives reconnect and each restored stream is silent", async () => scenario("live", async ({ current, sockets, frame, retry }) => {
  const socket = sockets.at(-1);
  await act(async () => socket.emit(frame(100, { live: { phase: "LIVE", status: "LIVE", paused: true, stale: false, delaySeconds: 30, requestedDelaySeconds: 30, navigationGeneration: 0 } })));
  assert.equal(current().isPlaying, false);
  assert.equal(current().sendReplayCommand({ type: "seek", at: at(50) }), false);
  assert.equal(current().sendReplayCommand({ type: "play", speed: 30 }), false);
  const generation = current().navigationGeneration;
  await act(async () => socket.close());
  await act(async () => retry());
  const query = new URL(sockets.at(-1).url).searchParams;
  assert.equal(query.get("live_paused_at"), at(100));
  assert.equal(query.get("delay_seconds"), "30");
  await act(async () => sockets.at(-1).emit(frame(100, { live: { phase: "LIVE", paused: true, delaySeconds: 40, requestedDelaySeconds: 40 } })));
  assert.ok(current().navigationGeneration > generation);
  assert.equal(current().liveDelaySeconds, 40);
  assert.equal(current().replayMoment(at(50)), false);
}));

test("forward navigation acknowledges a new generation after buffered snapshots and quietly seeds its destination", async () => scenario("replay", async ({ current, sockets, frame }) => {
  const socket = sockets.at(-1);
  const node = document.getElementById("viewer");
  const storyEvent = sequence => ({
    id: `event-${sequence}`, sessionKey: "A", kind: "FLAG", occurredAt: at(sequence), availableAt: at(sequence),
    availableSequence: sequence, driverNumbers: [], cause: "RED_FLAG", state: "confirmed", supersedes: null,
    priority: 3, lap: 10, phase: null, title: `Flag ${sequence}`, detail: "Source-confirmed flag", evidence: [], data: { flag: "RED_FLAG" },
  });
  const snapshot = (sequence, generation, events, playing = true) => frame(sequence, {
    playback: { playing, navigationGeneration: generation },
    analytics: { sessionKey: "A", sequence, context: { status: "ready" }, publishedStrategy: { baseline: { status: "PRESENT" } }, story: { sessionKey: "A", sequence, asOf: at(sequence), revision: String(sequence), events, modelVersion: "test", result: { state: "none", since: null } } },
  });
  await act(async () => socket.emit(snapshot(10, 0, [storyEvent(10)])));
  await act(async () => current().sendReplayCommand({ type: "seek", at: at(90) }));
  // A queued transport update still has the old server generation. It must
  // not consume the acknowledgement for the eventual forward destination.
  await act(async () => socket.emit(snapshot(11, 0, [storyEvent(10), storyEvent(11)])));
  const beforeAcknowledgement = current().navigationGeneration;
  await act(async () => socket.emit(snapshot(90, 1, [storyEvent(80), storyEvent(90)])));
  assert.ok(current().navigationGeneration > beforeAcknowledgement);
  assert.equal(node.querySelectorAll(".story-is-new").length, 0);
  assert.equal(node.querySelector(".story-moment"), null);
  await act(async () => socket.emit(snapshot(91, 1, [storyEvent(80), storyEvent(90), storyEvent(91)])));
  assert.equal(node.querySelectorAll(".story-is-new").length, 1);
  assert.match(node.querySelector(".story-moment").textContent, /Flag 91/);
}, value => createElement("div", null,
  createElement(StoryFeed, { story: value.analytics?.story, mode: "replay", generation: value.navigationGeneration }),
  createElement(StoryMoments, { story: value.analytics?.story, mode: "replay", generation: value.navigationGeneration, playing: value.isPlaying, speed: 1 }),
)));
