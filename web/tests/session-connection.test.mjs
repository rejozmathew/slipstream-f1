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

async function scenario(modeOrOptions, check) {
  const options = typeof modeOrOptions === "string" ? { mode: modeOrOptions } : (modeOrOptions ?? {});
  const mode = options.mode ?? "replay";
  const followLive = options.followLive ?? false;
  const initialSessionKey = options.selectedSessionKey ?? "A";
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
  let jobs = options.jobs ? [...options.jobs] : [];
  let current;
  let catalog = options.catalog ? JSON.parse(JSON.stringify(options.catalog)) : {
    defaultSessionKey: "A", liveSessionKey: mode === "live" ? "A" : null,
    sessions: ["A", "B"].map((sessionKey) => ({ sessionKey, available: false, liveAvailable: mode === "live" && sessionKey === "A" })),
  };
  let downloadHandler = options.downloadHandler ?? ((sessionKey) => {
    const job = { sessionKey, status: "DOWNLOADING", error: null };
    jobs = [job];
    return job;
  });
  let stateHandler = options.stateHandler ?? (async () => { throw new Error("Test REST offline; reconnect uses stream"); });
  const setJobs = (next) => { jobs = typeof next === "function" ? next(jobs) : next; };
  const setCatalog = (next) => { catalog = typeof next === "function" ? next(catalog) : next; };
  const setDownloadHandler = (fn) => { downloadHandler = fn; };
  const setStateHandler = (fn) => { stateHandler = fn; };
  const setAnalyticsHandler = (fn) => { slipstreamApi.analytics = fn; };
  slipstreamApi.catalog = async () => catalog;
  slipstreamApi.jobs = async () => ({ jobs });
  slipstreamApi.download = async (sessionKey) => downloadHandler(sessionKey);
  slipstreamApi.state = async (...args) => stateHandler(...args);
  slipstreamApi.analytics = async () => { throw new Error("Optional analytics absent"); };
  window.localStorage.clear();
  window.localStorage.setItem("slipstream.selected-session.v1", initialSessionKey);
  window.localStorage.setItem("slipstream.viewing-intent.v2", JSON.stringify({ mode, followLive }));
  const root = createRoot(document.getElementById("root"));
  function Host() { current = useSlipstreamSession(); return null; }
  const frame = (seq, available, extra = {}) => {
    const sessionKey = extra.sessionKey ?? extra.data?.session?.key ?? "A";
    return {
      v: 1, type: "state.snapshot", seq, sessionTime: "2026-06-14T13:00:00Z", playback: { playing: false },
      data: { ...EMPTY_RACE_STATE, session: { ...EMPTY_RACE_STATE.session, key: sessionKey }, ...extra.data },
      metadata: { available, replayAvailable: available, sessionKey, ...extra.metadata },
      capabilities: { v: 1, source: "test", capabilities: {}, replayAvailable: available, liveAvailable: mode === "live", ...extra.capabilities },
      playbackReady: true,
      live: { phase: "LIVE", status: "LIVE", delaySeconds: 0, positionMode: "unavailable", ...extra.live },
      ...extra,
    };
  };
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
    await check({ sockets, frame, complete, current: () => current, runTimer, setJobs, setCatalog, setDownloadHandler, setStateHandler, setAnalyticsHandler, getJobs: () => jobs, getCatalog: () => catalog });
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

test("a same-recording transport reconnect retains its valid cursor", async () => scenario({
  mode: "replay",
  catalog: {
    defaultSessionKey: "A",
    liveSessionKey: null,
    sessions: [
      { sessionKey: "A", available: true, recordingVersion: "rec-v1", liveAvailable: false },
      { sessionKey: "B", available: false, recordingVersion: null, liveAvailable: false },
    ],
  },
}, async ({ sockets, frame, current, runTimer }) => {
  await act(async () => sockets.at(-1).emit(frame(114, true, {
    metadata: { sessionKey: "A", available: true, replayAvailable: true, recordingVersion: "rec-v1" },
  })));
  await act(async () => sockets.at(-1).close());
  await act(async () => runTimer(500, false));
  assert.equal(new URL(sockets.at(-1).url).searchParams.get("seq"), "114");
  assert.equal(new URL(sockets.at(-1).url).searchParams.get("recording_version"), "rec-v1");
  await act(async () => sockets.at(-1).emit(frame(114, true, {
    metadata: { sessionKey: "A", available: true, replayAvailable: true, recordingVersion: "rec-v1" },
  })));
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
  await act(async () => sockets.at(-1).emit(frame(250, true, { metadata: { sessionKey: "A", available: true, recordingVersion: "published-v1" }, mode: "replay", handoff: "REPLAY_READY" })));
  assert.equal(sockets.length, 2);
  assert.equal(new URL(sockets.at(-1).url).searchParams.get("seq"), "250");
  assert.equal(new URL(sockets.at(-1).url).searchParams.get("recording_version"), "published-v1");
  assert.equal(current().viewingMode, "replay");
}));

test("first jobs observation already AVAILABLE replaces selected unavailable placeholder", async () => scenario("replay", async ({ sockets, frame, current, runTimer, setJobs, setCatalog }) => {
  await act(async () => sockets.at(-1).emit(frame(2, false)));
  assert.equal(current().metadata.available, false);
  assert.equal(sockets.length, 1);

  setJobs([{ sessionKey: "A", status: "AVAILABLE", error: null }]);
  setCatalog((cat) => ({
    ...cat,
    sessions: cat.sessions.map((s) => s.sessionKey === "A" ? { ...s, available: true } : s),
  }));

  await act(async () => runTimer(2000, true));
  assert.equal(sockets.length, 2, "First jobs observation of AVAILABLE must replace unavailable placeholder");
  assert.equal(new URL(sockets.at(-1).url).searchParams.get("seq"), null);

  await act(async () => sockets.at(-1).emit(frame(10, true)));
  assert.equal(current().sequence, 10);
  assert.equal(current().metadata.available, true);
}));

test("a newly reported recording version replaces a replay with no prior version", async () => scenario("replay", async ({ sockets, frame, runTimer, setCatalog }) => {
  await act(async () => sockets.at(-1).emit(frame(80, true)));
  setCatalog((cat) => ({ ...cat, sessions: cat.sessions.map((item) => ({ ...item, available: true, recordingVersion: "published-v1" })) }));
  await act(async () => runTimer(15000, true));
  assert.equal(sockets.length, 2);
  assert.equal(new URL(sockets.at(-1).url).searchParams.get("seq"), null);
  await act(async () => sockets.at(-1).emit(frame(0, true, { metadata: { available: true, recordingVersion: "published-v1" } })));
  await act(async () => runTimer(15000, true));
  assert.equal(sockets.length, 2, "The same published version must not reopen repeatedly");
}));

test("immediate POST AVAILABLE replaces placeholder", async () => scenario("replay", async ({ sockets, frame, current, setDownloadHandler, setCatalog }) => {
  await act(async () => sockets.at(-1).emit(frame(2, false)));
  assert.equal(current().metadata.available, false);
  assert.equal(sockets.length, 1);

  setDownloadHandler(async (sessionKey) => ({ sessionKey, status: "AVAILABLE", error: null }));
  setCatalog((cat) => ({
    ...cat,
    sessions: cat.sessions.map((s) => s.sessionKey === "A" ? { ...s, available: true } : s),
  }));

  await act(async () => current().downloadReplay());

  assert.equal(sockets.length, 2, "Immediate POST AVAILABLE must replace placeholder");
  assert.equal(new URL(sockets.at(-1).url).searchParams.get("seq"), null);

  await act(async () => sockets.at(-1).emit(frame(15, true)));
  assert.equal(current().sequence, 15);
  assert.equal(current().metadata.available, true);
}));

test("catalog available true replaces placeholder even no jobs", async () => scenario("replay", async ({ sockets, frame, current, runTimer, setJobs, setCatalog }) => {
  await act(async () => sockets.at(-1).emit(frame(2, false)));
  assert.equal(current().metadata.available, false);
  assert.equal(sockets.length, 1);

  setJobs([]);
  setCatalog((cat) => ({
    ...cat,
    sessions: cat.sessions.map((s) => s.sessionKey === "A" ? { ...s, available: true } : s),
  }));

  await act(async () => runTimer(15000, true));
  assert.equal(sockets.length, 2, "Catalog available true must replace placeholder even no jobs");
  assert.equal(new URL(sockets.at(-1).url).searchParams.get("seq"), null);

  await act(async () => sockets.at(-1).emit(frame(20, true)));
  assert.equal(current().sequence, 20);
  assert.equal(current().metadata.available, true);
}));

test("changed recordingVersion on selected available resource replaces old recording without stale seq", async () => scenario({
  mode: "replay",
  catalog: {
    defaultSessionKey: "A",
    liveSessionKey: null,
    sessions: [
      { sessionKey: "A", available: true, recordingVersion: "rec-v1", liveAvailable: false },
      { sessionKey: "B", available: false, recordingVersion: null, liveAvailable: false },
    ],
  },
}, async ({ sockets, frame, current, runTimer, setCatalog }) => {
  await act(async () => sockets.at(-1).emit(frame(75, true, {
    metadata: { sessionKey: "A", available: true, replayAvailable: true, recordingVersion: "rec-v1" },
  })));
  assert.equal(current().sequence, 75);
  assert.equal(current().metadata.available, true);
  assert.equal(current().metadata.recordingVersion, "rec-v1");
  assert.equal(sockets.length, 1);

  setCatalog((cat) => ({
    ...cat,
    sessions: cat.sessions.map((s) => s.sessionKey === "A" ? { ...s, recordingVersion: "rec-v2" } : s),
  }));

  await act(async () => runTimer(15000, true));
  assert.equal(sockets.length, 2, "Changed recordingVersion on selected resource must replace old recording");
  assert.equal(new URL(sockets.at(-1).url).searchParams.get("seq"), null, "New recording version connection must not carry stale seq");

  await act(async () => sockets.at(-1).emit(frame(1, true, {
    metadata: { sessionKey: "A", available: true, replayAvailable: true, recordingVersion: "rec-v2" },
  })));
  assert.equal(current().sequence, 1);
  assert.equal(current().metadata.recordingVersion, "rec-v2");
}));

test("repeated unchanged AVAILABLE/catalog does not reopen healthy stream", async () => scenario({
  mode: "replay",
  catalog: {
    defaultSessionKey: "A",
    liveSessionKey: null,
    sessions: [
      { sessionKey: "A", available: true, recordingVersion: "rec-v1", liveAvailable: false },
      { sessionKey: "B", available: false, recordingVersion: null, liveAvailable: false },
    ],
  },
}, async ({ sockets, frame, current, runTimer, setJobs }) => {
  await act(async () => sockets.at(-1).emit(frame(100, true, {
    metadata: { sessionKey: "A", available: true, replayAvailable: true, recordingVersion: "rec-v1" },
  })));
  assert.equal(current().sequence, 100);
  assert.equal(current().commandAvailable, true);
  assert.equal(current().transport, "stream");
  const establishedCount = sockets.length;

  setJobs([{ sessionKey: "A", status: "AVAILABLE", error: null }]);
  await act(async () => runTimer(2000, true));
  await act(async () => runTimer(15000, true));
  await act(async () => runTimer(2000, true));
  await act(async () => runTimer(15000, true));

  assert.equal(sockets.length, establishedCount, "Repeated unchanged AVAILABLE/catalog must not reopen healthy stream");
  assert.equal(sockets.at(-1).readyState, 1);
  assert.equal(current().sequence, 100);
  assert.equal(current().commandAvailable, true);
}));

test("Follow Live with A unavailable and B current advances, but explicit selection and delayed old tail remain A", async () => {
  await scenario({
    mode: "live",
    followLive: true,
    catalog: {
      defaultSessionKey: "A",
      liveSessionKey: "A",
      sessions: [
        { sessionKey: "A", available: false, liveAvailable: true },
        { sessionKey: "B", available: false, liveAvailable: true },
      ],
    },
  }, async ({ sockets, frame, current, runTimer, setCatalog }) => {
    await act(async () => sockets.at(-1).emit(frame(50, false, {
      live: { phase: "UNAVAILABLE", status: "OFFLINE", delaySeconds: 0 },
    })));
    assert.equal(current().selectedSessionKey, "A");

    setCatalog((cat) => ({ ...cat, liveSessionKey: "B" }));
    await act(async () => runTimer(15000, true));

    assert.equal(current().selectedSessionKey, "B", "Follow Live viewer must advance to B when A is unavailable");
    assert.equal(current().viewingMode, "live");
  });

  await scenario({
    mode: "live",
    followLive: false,
    catalog: {
      defaultSessionKey: "A",
      liveSessionKey: "A",
      sessions: [
        { sessionKey: "A", available: false, liveAvailable: true },
        { sessionKey: "B", available: false, liveAvailable: true },
      ],
    },
  }, async ({ sockets, frame, current, runTimer, setCatalog }) => {
    await act(async () => sockets.at(-1).emit(frame(50, false, {
      live: { phase: "UNAVAILABLE", status: "OFFLINE", delaySeconds: 0 },
    })));
    assert.equal(current().selectedSessionKey, "A");

    setCatalog((cat) => ({ ...cat, liveSessionKey: "B" }));
    await act(async () => runTimer(15000, true));

    assert.equal(current().selectedSessionKey, "A", "Explicit viewer must remain on A even when B becomes current");
  });

  await scenario({
    mode: "live",
    followLive: true,
    catalog: {
      defaultSessionKey: "A",
      liveSessionKey: "A",
      sessions: [
        { sessionKey: "A", available: false, liveAvailable: true },
        { sessionKey: "B", available: false, liveAvailable: true },
      ],
    },
  }, async ({ sockets, frame, current, runTimer, setCatalog }) => {
    await act(async () => sockets.at(-1).emit(frame(50, false, {
      live: { phase: "LIVE", status: "LIVE", delaySeconds: 0 },
    })));
    assert.equal(current().commandAvailable, true);
    const sent = current().sendReplayCommand({ type: "delay", seconds: 30 });
    assert.equal(sent, true);

    await act(async () => sockets.at(-1).emit(frame(51, false, {
      live: { phase: "UNAVAILABLE", status: "OFFLINE", delaySeconds: 30 },
    })));

    setCatalog((cat) => ({ ...cat, liveSessionKey: "B" }));
    await act(async () => runTimer(15000, true));

    assert.equal(current().selectedSessionKey, "A", "Delayed viewer must remain on A until delayed tail is consumed");
  });
});

test("live.nextSessionKey=B is a server signal emitted only once retained delayed tail is consumed; following viewer advances but explicit viewer stays", async () => {
  await scenario({
    mode: "live",
    followLive: true,
    catalog: {
      defaultSessionKey: "A",
      liveSessionKey: "A",
      sessions: [
        { sessionKey: "A", available: false, liveAvailable: true },
        { sessionKey: "B", available: false, liveAvailable: true },
      ],
    },
  }, async ({ sockets, frame, current }) => {
    await act(async () => sockets.at(-1).emit(frame(80, false, {
      live: { phase: "STALE", status: "OFFLINE", delaySeconds: 15 },
    })));
    assert.equal(current().selectedSessionKey, "A");

    await act(async () => sockets.at(-1).emit(frame(85, false, {
      live: { phase: "STALE", status: "OFFLINE", delaySeconds: 0, nextSessionKey: "B" },
    })));

    assert.equal(current().selectedSessionKey, "B", "Following viewer must advance when live.nextSessionKey is emitted");
    assert.equal(current().viewingMode, "live");
  });

  await scenario({
    mode: "live",
    followLive: false,
    catalog: {
      defaultSessionKey: "A",
      liveSessionKey: "A",
      sessions: [
        { sessionKey: "A", available: false, liveAvailable: true },
        { sessionKey: "B", available: false, liveAvailable: true },
      ],
    },
  }, async ({ sockets, frame, current }) => {
    await act(async () => sockets.at(-1).emit(frame(80, false, {
      live: { phase: "STALE", status: "OFFLINE", delaySeconds: 15 },
    })));
    assert.equal(current().selectedSessionKey, "A");

    await act(async () => sockets.at(-1).emit(frame(85, false, {
      live: { phase: "STALE", status: "OFFLINE", delaySeconds: 0, nextSessionKey: "B" },
    })));

    assert.equal(current().selectedSessionKey, "A", "Explicit viewer must stay on A when nextSessionKey is emitted");
  });
});

test("reconnect after file replacement before catalog poll adopts new version start without stale seq", async () => scenario({
  mode: "replay",
  catalog: {
    defaultSessionKey: "A",
    liveSessionKey: null,
    sessions: [
      { sessionKey: "A", available: true, recordingVersion: "rec-v1", liveAvailable: false },
      { sessionKey: "B", available: false, recordingVersion: null, liveAvailable: false },
    ],
  },
}, async ({ sockets, frame, current, runTimer, setCatalog }) => {
  await act(async () => sockets.at(-1).emit(frame(80, true, {
    metadata: { sessionKey: "A", available: true, replayAvailable: true, recordingVersion: "rec-v1" },
  })));
  assert.equal(current().sequence, 80);
  assert.equal(current().metadata.recordingVersion, "rec-v1");
  assert.equal(current().commandAvailable, true);
  assert.equal(sockets.length, 1);

  await act(async () => sockets.at(-1).close());
  await act(async () => runTimer(500, false));
  assert.equal(sockets.length, 2);

  const reconnectUrl = new URL(sockets.at(-1).url);
  assert.equal(reconnectUrl.searchParams.get("seq"), "80");
  assert.equal(reconnectUrl.searchParams.get("recording_version"), "rec-v1");

  // Server detects identity mismatch and returns official start of new version rec-v2
  await act(async () => sockets.at(-1).emit(frame(5, true, {
    metadata: { sessionKey: "A", available: true, replayAvailable: true, recordingVersion: "rec-v2" },
  })));

  assert.equal(current().sequence, 5, "Client must adopt server start sequence of replacement recording instead of stale cursor 80");
  assert.equal(current().metadata.recordingVersion, "rec-v2");
  assert.equal(current().commandAvailable, true);
  assert.equal(sockets.length, 2, "Client must accept reset once without unnecessary extra reopen");

  // Subsequent catalog poll confirms rec-v2; healthy stream must not reopen
  setCatalog((cat) => ({
    ...cat,
    sessions: cat.sessions.map((s) => s.sessionKey === "A" ? { ...s, recordingVersion: "rec-v2" } : s),
  }));
  await act(async () => runTimer(15000, true));
  assert.equal(sockets.length, 2, "Stream must remain open when catalog catches up to rec-v2");
  assert.equal(current().sequence, 5);
  assert.equal(current().metadata.recordingVersion, "rec-v2");
}));

test("matching unchanged recording resume retains valid cursor with recording identity", async () => scenario({
  mode: "replay",
  catalog: {
    defaultSessionKey: "A",
    liveSessionKey: null,
    sessions: [
      { sessionKey: "A", available: true, recordingVersion: "rec-v1", liveAvailable: false },
      { sessionKey: "B", available: false, recordingVersion: null, liveAvailable: false },
    ],
  },
}, async ({ sockets, frame, current, runTimer }) => {
  await act(async () => sockets.at(-1).emit(frame(120, true, {
    metadata: { sessionKey: "A", available: true, replayAvailable: true, recordingVersion: "rec-v1" },
  })));
  assert.equal(current().sequence, 120);
  assert.equal(current().metadata.recordingVersion, "rec-v1");
  assert.equal(current().commandAvailable, true);

  await act(async () => sockets.at(-1).close());
  await act(async () => runTimer(500, false));
  assert.equal(sockets.length, 2);

  const reconnectUrl = new URL(sockets.at(-1).url);
  assert.equal(reconnectUrl.searchParams.get("seq"), "120");
  assert.equal(reconnectUrl.searchParams.get("recording_version"), "rec-v1");

  await act(async () => sockets.at(-1).emit(frame(120, true, {
    metadata: { sessionKey: "A", available: true, replayAvailable: true, recordingVersion: "rec-v1" },
  })));
  assert.equal(current().sequence, 120);
  assert.equal(current().metadata.recordingVersion, "rec-v1");
  assert.equal(current().commandAvailable, true);
  assert.equal(current().transport, "stream");
}));

test("a cursor with no known recording version is not automatically reused on reconnect", async () => scenario("replay", async ({ sockets, frame, current, runTimer }) => {
  await act(async () => sockets.at(-1).emit(frame(75, true, {
    metadata: { sessionKey: "A", available: true, replayAvailable: true, recordingVersion: null },
  })));
  assert.equal(current().sequence, 75);
  assert.equal(current().metadata.recordingVersion, null);

  await act(async () => sockets.at(-1).close());
  await act(async () => runTimer(500, false));

  const reconnectUrl = new URL(sockets.at(-1).url);
  assert.equal(reconnectUrl.searchParams.get("seq"), null, "Cursor without known version must not be automatically reused");
  assert.equal(reconnectUrl.searchParams.get("recording_version"), null);
}));

test("REST fallback after disconnected WS sends recording identity and applies state", async () => {
  const stateCalls = [];
  await scenario({
    mode: "replay",
    stateHandler: async (sessionKey, mode, seq, delay, version) => {
      stateCalls.push({ sessionKey, mode, seq, delay, version });
      return {
        v: 1, type: "state.snapshot", seq: 52, sessionTime: "2026-06-14T13:00:00Z", playback: { playing: false },
        data: { ...EMPTY_RACE_STATE, session: { ...EMPTY_RACE_STATE.session, key: sessionKey } },
        metadata: { available: true, replayAvailable: true, sessionKey, recordingVersion: "rec-v1" },
        capabilities: { v: 1, source: "test", capabilities: {}, replayAvailable: true, liveAvailable: false },
        playbackReady: true,
        live: { phase: "LIVE", status: "LIVE", delaySeconds: 0, positionMode: "unavailable" },
      };
    },
  }, async ({ sockets, frame, current }) => {
    await act(async () => sockets.at(-1).emit(frame(50, true, {
      metadata: { sessionKey: "A", available: true, replayAvailable: true, recordingVersion: "rec-v1" },
    })));
    assert.equal(current().sequence, 50);
    assert.equal(current().metadata.recordingVersion, "rec-v1");
    assert.equal(current().transport, "stream");

    await act(async () => sockets.at(-1).close());

    assert.ok(stateCalls.length >= 1, "REST fallback must be triggered on WS disconnect");
    const lastCall = stateCalls.at(-1);
    assert.equal(lastCall.sessionKey, "A");
    assert.equal(lastCall.mode, "replay");
    assert.equal(lastCall.seq, 50);
    assert.equal(lastCall.version, "rec-v1", "REST fallback must supply known recordingVersion");

    assert.equal(current().transport, "rest");
    assert.equal(current().sequence, 52);
    assert.equal(current().metadata.recordingVersion, "rec-v1");
    assert.equal(current().commandAvailable, false);
  });
});

test("REST fallback with replaced recording adopts new version start without extra reopen", async () => {
  const stateCalls = [];
  await scenario({
    mode: "replay",
    stateHandler: async (sessionKey, mode, seq, delay, version) => {
      stateCalls.push({ sessionKey, mode, seq, delay, version });
      return {
        v: 1, type: "state.snapshot", seq: 10, sessionTime: "2026-06-14T13:00:00Z", playback: { playing: false },
        data: { ...EMPTY_RACE_STATE, session: { ...EMPTY_RACE_STATE.session, key: sessionKey } },
        metadata: { available: true, replayAvailable: true, sessionKey, recordingVersion: "rec-v2" },
        capabilities: { v: 1, source: "test", capabilities: {}, replayAvailable: true, liveAvailable: false },
        playbackReady: true,
        live: { phase: "LIVE", status: "LIVE", delaySeconds: 0, positionMode: "unavailable" },
      };
    },
  }, async ({ sockets, frame, current }) => {
    await act(async () => sockets.at(-1).emit(frame(50, true, {
      metadata: { sessionKey: "A", available: true, replayAvailable: true, recordingVersion: "rec-v1" },
    })));
    assert.equal(current().sequence, 50);

    await act(async () => sockets.at(-1).close());

    assert.ok(stateCalls.length >= 1);
    assert.equal(stateCalls.at(-1).version, "rec-v1");

    assert.equal(current().transport, "rest");
    assert.equal(current().sequence, 10, "REST fallback must adopt official start sequence of new recording version");
    assert.equal(current().metadata.recordingVersion, "rec-v2");
  });
});

test("ignoring late former-generation REST responses after newer stream reconnect", async () => {
  let resolveRest;
  let restCount = 0;
  await scenario({
    mode: "replay",
    stateHandler: async () => {
      restCount++;
      return new Promise((resolve) => {
        resolveRest = resolve;
      });
    },
  }, async ({ sockets, frame, current, runTimer }) => {
    await act(async () => sockets.at(-1).emit(frame(40, true, {
      metadata: { sessionKey: "A", available: true, replayAvailable: true, recordingVersion: "rec-v1" },
    })));
    assert.equal(current().sequence, 40);
    assert.equal(current().transport, "stream");
    assert.equal(sockets.length, 1);

    await act(async () => sockets.at(-1).close());
    assert.equal(restCount, 1, "REST fallback should be initiated on socket close");

    await act(async () => runTimer(500, false));
    assert.equal(sockets.length, 2);

    await act(async () => sockets.at(-1).emit(frame(65, true, {
      metadata: { sessionKey: "A", available: true, replayAvailable: true, recordingVersion: "rec-v1" },
    })));
    assert.equal(current().sequence, 65);
    assert.equal(current().transport, "stream");
    assert.equal(current().commandAvailable, true);

    // Socket 2 drops before late REST 1 resolves, resetting streamReady
    await act(async () => sockets.at(-1).close());

    // Former-generation REST response resolves late with stale sequence 42
    await act(async () => {
      resolveRest?.(frame(42, true, {
        metadata: { sessionKey: "A", available: true, replayAvailable: true, recordingVersion: "rec-v1" },
      }));
    });

    assert.equal(current().sequence, 65, "Late former-generation REST response must not overwrite newer sequence");
  });
});

test("late REST fallback cannot overwrite an accepted snapshot followed by disconnect in the same generation", async () => scenario("replay", async ({ sockets, frame, runTimer, setStateHandler, current }) => {
  let resolveRest;
  setStateHandler(() => new Promise((resolve) => { resolveRest = resolve; }));
  await act(async () => runTimer(3000, true));
  assert.equal(typeof resolveRest, "function");
  await act(async () => sockets.at(-1).emit(frame(70, true, {
    metadata: { sessionKey: "A", available: true, recordingVersion: "v1" },
  })));
  await act(async () => sockets.at(-1).close());
  await act(async () => resolveRest(frame(1, true, {
    metadata: { sessionKey: "A", available: true, recordingVersion: "v1" },
  })));
  assert.equal(current().sequence, 70);
  assert.equal(sockets.length, 1);
}));

test("analytics from a replaced recording cannot attach to the same numeric cursor", async () => scenario("replay", async ({ sockets, frame, runTimer, setAnalyticsHandler, current }) => {
  let resolveOld;
  const result = (version) => ({ sessionKey: "A", sequence: 80, recordingVersion: version,
    context: { status: "ready" }, publishedStrategy: { baseline: { status: "PRESENT" } } });
  const calls = [];
  setAnalyticsHandler((key, seq, version) => {
    calls.push([key, seq, version]);
    return version === "v1" ? new Promise((resolve) => { resolveOld = resolve; }) : Promise.resolve(result(version));
  });
  await act(async () => sockets.at(-1).emit(frame(80, true, {
    metadata: { sessionKey: "A", available: true, recordingVersion: "v1" },
  })));
  await act(async () => sockets.at(-1).close());
  await act(async () => runTimer(500, false));
  await act(async () => sockets.at(-1).emit(frame(80, true, {
    metadata: { sessionKey: "A", available: true, recordingVersion: "v2" },
  })));
  await act(async () => resolveOld(result("v1")));
  assert.notEqual(current().analytics?.recordingVersion, "v1");
  await act(async () => sockets.at(-1).emit(frame(80, true, {
    metadata: { sessionKey: "A", available: true, recordingVersion: "v2" },
  })));
  assert.equal(current().analytics.recordingVersion, "v2");
  assert.deepEqual(calls.at(-1), ["A", 80, "v2"]);
}));

test("handoff with unknown recording identity does not automatically reuse its cursor", async () => scenario("live", async ({ sockets, frame, current }) => {
  await act(async () => sockets.at(-1).emit(frame(250, true, {
    metadata: { sessionKey: "A", available: true, recordingVersion: null },
    mode: "replay", handoff: "REPLAY_READY",
  })));
  assert.equal(current().viewingMode, "replay");
  assert.equal(sockets.length, 2);
  assert.equal(new URL(sockets.at(-1).url).searchParams.get("seq"), null);
}));
