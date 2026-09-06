import assert from "node:assert/strict";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { act, createElement } from "react";
import { JSDOM } from "jsdom";
import { createServer } from "vite";

const dom = new JSDOM("<div id='root'></div>", { url: "http://localhost" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import("react-dom/client");
const server = await createServer({ configLoader: "runner", cacheDir: "../.codex-tmp/vite-connection-tests", root: fileURLToPath(new URL("..", import.meta.url)), server: { middlewareMode: true, hmr: false, ws: false }, appType: "custom" });
after(async () => { await server.close(); dom.window.close(); });
const { slipstreamApi } = await server.ssrLoadModule("/api/client.ts");
const { useSlipstreamSession } = await server.ssrLoadModule("/hooks/useSlipstreamSession.ts");
const { EMPTY_RACE_STATE } = await server.ssrLoadModule("/domain/protocol.ts");

async function scenario(mode, check) {
  const savedApi = { ...slipstreamApi };
  const savedSocket = globalThis.WebSocket;
  const savedTimers = Object.fromEntries(["setTimeout", "clearTimeout", "setInterval", "clearInterval"].map((key) => [key, window[key]]));
  const timers = new Map();
  let timerId = 0;
  for (const [set, clear, repeat] of [["setTimeout", "clearTimeout", false], ["setInterval", "clearInterval", true]]) {
    window[set] = (callback, delay) => { timers.set(++timerId, { callback, delay, repeat }); return timerId; };
    window[clear] = (id) => timers.delete(id);
  }
  const sockets = [];
  globalThis.WebSocket = class {
    static OPEN = 1;
    readyState = 1;
    constructor(url) { this.url = url; sockets.push(this); }
    close() { if (this.readyState !== 3) { this.readyState = 3; this.onclose?.(); } }
    send() {}
    emit(frame) { this.onmessage?.({ data: JSON.stringify(frame) }); }
  };
  let jobs = [];
  let current;
  const catalog = {
    defaultSessionKey: "A", liveSessionKey: mode === "live" ? "A" : null,
    sessions: ["A", "B"].map((sessionKey) => ({ sessionKey, available: false, liveAvailable: mode === "live" && sessionKey === "A" })),
  };
  slipstreamApi.catalog = async () => catalog;
  slipstreamApi.jobs = async () => ({ jobs });
  slipstreamApi.download = async (sessionKey) => {
    const job = { sessionKey, status: "DOWNLOADING", error: null };
    jobs = [job];
    return job;
  };
  slipstreamApi.state = async () => { throw new Error("Test REST offline; reconnect uses stream"); };
  slipstreamApi.analytics = async () => { throw new Error("Optional analytics absent"); };
  window.localStorage.clear();
  window.localStorage.setItem("slipstream.selected-session.v1", "A");
  window.localStorage.setItem("slipstream.viewing-intent.v2", JSON.stringify({ mode, followLive: false }));
  const root = createRoot(document.getElementById("root"));
  function Host() { current = useSlipstreamSession(); return null; }
  const frame = (seq, available, extra = {}) => ({
    v: 1, type: "state.snapshot", seq, sessionTime: "2026-06-14T13:00:00Z", playback: { playing: false },
    data: { ...EMPTY_RACE_STATE, session: { ...EMPTY_RACE_STATE.session, key: "A" } },
    metadata: { available, replayAvailable: available }, capabilities: {}, playbackReady: true,
    live: { phase: "LIVE", status: "LIVE", delaySeconds: 0, positionMode: "unavailable" }, ...extra,
  });
  const runTimer = async (delay, repeat) => {
    const selected = [...timers].filter(([, value]) => value.delay === delay && value.repeat === repeat);
    assert.ok(selected.length, `Timer ${delay}/${repeat} is scheduled`);
    for (const [id, timer] of selected) {
      if (!repeat) timers.delete(id);
      await timer.callback();
    }
  };
  const complete = async (sessionKey = "A", trailingFrame) => {
    jobs = [{ sessionKey, status: "AVAILABLE", error: null }];
    await act(async () => {
      await runTimer(2000, true);
      // Deliver an old transport packet before React cleans up that connection.
      if (trailingFrame) sockets.at(-1).emit(trailingFrame);
    });
  };
  try {
    await act(async () => root.render(createElement(Host)));
    await check({ sockets, frame, complete, current: () => current, runTimer });
  } finally {
    await act(async () => root.unmount());
    Object.assign(slipstreamApi, savedApi);
    Object.assign(window, savedTimers);
    globalThis.WebSocket = savedSocket;
  }
}

test("placeholder reconnect and first download never reuse catalog event counts", async () => scenario("replay", async ({ sockets, frame, complete, current, runTimer }) => {
  await act(async () => sockets.at(-1).emit(frame(2, false)));
  await act(async () => sockets.at(-1).close());
  await act(async () => runTimer(500, false));
  assert.equal(new URL(sockets.at(-1).url).searchParams.get("seq"), null);
  await act(async () => sockets.at(-1).emit(frame(2, false)));
  await act(async () => current().downloadReplay());
  await complete("A", frame(2, false));
  assert.equal(sockets.length, 3);
  assert.equal(new URL(sockets.at(-1).url).searchParams.get("seq"), null);
}));

test("a same-recording transport reconnect retains its valid cursor", async () => scenario("replay", async ({ sockets, frame, current, runTimer }) => {
  await act(async () => sockets.at(-1).emit(frame(114, true)));
  await act(async () => sockets.at(-1).close());
  await act(async () => runTimer(500, false));
  assert.equal(new URL(sockets.at(-1).url).searchParams.get("seq"), "114");
  await act(async () => sockets.at(-1).emit(frame(114, true)));
  assert.equal(current().sequence, 114);
  assert.equal(current().commandAvailable, true);
}));

test("replacement downloads reject even a trailing cursor from the previous recording", async () => scenario("replay", async ({ sockets, frame, complete, current }) => {
  await act(async () => sockets.at(-1).emit(frame(80, true)));
  await act(async () => current().downloadReplay());
  await complete("A", frame(81, true));
  assert.equal(sockets.length, 2);
  assert.equal(new URL(sockets.at(-1).url).searchParams.get("seq"), null);
}));

test("a background download does not reconnect another selected replay", async () => scenario("replay", async ({ sockets, frame, complete, current }) => {
  await act(async () => sockets.at(-1).emit(frame(2, false)));
  await act(async () => current().downloadReplay());
  await act(async () => current().chooseSession("B", "replay"));
  const connection = sockets.at(-1);
  await act(async () => connection.emit(frame(90, true)));
  await complete();
  assert.equal(sockets.at(-1), connection);
  assert.equal(current().selectedSessionKey, "B");
  assert.equal(current().sequence, 90);
  assert.equal(current().commandAvailable, true);
}));

test("Live survives replay publication and retains the drained cursor on handoff", async () => scenario("live", async ({ sockets, frame, complete, current }) => {
  await act(async () => sockets.at(-1).emit(frame(200, false)));
  await act(async () => current().downloadReplay());
  await complete();
  assert.equal(sockets.length, 1, "Replay publication must not interrupt Live");
  assert.equal(current().viewingMode, "live");
  assert.equal(current().commandAvailable, true);
  await act(async () => sockets.at(-1).emit(frame(250, false, { metadata: undefined, mode: "replay", handoff: "REPLAY_READY" })));
  assert.equal(sockets.length, 2);
  assert.equal(new URL(sockets.at(-1).url).searchParams.get("seq"), "250");
  assert.equal(current().viewingMode, "replay");
}));
