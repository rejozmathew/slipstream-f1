import assert from "node:assert/strict";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { act, createElement } from "react";
import { createServer } from "vite";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<div id='story-test'></div>", { url: "http://localhost" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import("react-dom/client");
const server = await createServer({ configLoader: "runner", cacheDir: "../.codex-tmp/vite-story-tests", root: fileURLToPath(new URL("..", import.meta.url)), server: { middlewareMode: true, hmr: false }, appType: "custom" });
after(async () => { await server.close(); dom.window.close(); });
const { StoryFeed } = await server.ssrLoadModule("/components/story/StoryFeed.tsx");
const { StoryMoments } = await server.ssrLoadModule("/components/story/StoryMoments.tsx");
const { slipstreamApi } = await server.ssrLoadModule("/api/client.ts");
const event = (sequence, extra = {}) => ({ id: String(sequence), sessionKey: "s", kind: "PASS", occurredAt: "2026-07-26T13:01:00+00:00", availableAt: "2026-07-26T13:01:05+00:00", availableSequence: sequence, driverNumbers: ["1", "2"], cause: "ON_TRACK", state: "confirmed", supersedes: null, priority: 3, lap: 12, phase: null, title: `Pass ${sequence}`, detail: "Confirmed after both cars report progress", evidence: [], data: {}, ...extra });
const snapshot = (sequence, events) => ({ sequence, events, asOf: "2026-07-26T13:02:00+00:00", modelVersion: "test", revision: String(sequence), result: { state: "none", since: null } });

test("inspect and replay are separate and navigation silently rebuilds feed", async () => {
  const node = document.getElementById("story-test");
  const root = createRoot(node);
  const replayed = [];
  const render = (story, generation = 0, mode = "replay") => act(() => root.render(createElement(StoryFeed, { story, generation, mode, onReplay: value => replayed.push(value.id) })));
  await render(snapshot(1, [event(1)]));
  assert.equal(node.querySelectorAll(".story-is-new").length, 0);
  await act(() => node.querySelector(".story-inspect").click());
  assert.equal(replayed.length, 0);
  assert.match(node.textContent, /Happened.*Known.*Status/);
  await act(() => node.querySelector(".story-replay").click());
  assert.deepEqual(replayed, ["1"]);
  await render(snapshot(2, [event(1), event(2)]));
  assert.equal(node.querySelectorAll(".story-is-new").length, 1);
  await render(snapshot(20, [event(20)]), 1);
  assert.equal(node.querySelectorAll(".story-is-new").length, 0);
  assert.equal(node.querySelector(".story-facts"), null);
  await render(snapshot(20, [event(20)]), 2, "live");
  await act(() => node.querySelector(".story-inspect").click());
  assert.equal(node.querySelector(".story-replay"), null);
  assert.match(node.textContent, /when the recording is available/);
  await act(() => root.unmount());
});

test("moments do not announce initial history, seeks, pauses, or ordinary events at20x", async () => {
  const node = document.getElementById("story-test");
  const root = createRoot(node);
  const render = (sequence, generation, extra = {}) => act(() => root.render(createElement(StoryMoments, { story: snapshot(sequence, [event(sequence)]), generation, mode: "replay", ...extra })));
  await render(10, 0);
  assert.equal(node.textContent, "");
  await render(11, 0);
  assert.match(node.textContent, /Pass 11/);
  await render(100, 1);
  assert.equal(node.textContent, "");
  await render(101, 1, { playing: false });
  assert.equal(node.textContent, "");
  await render(102, 1, { speed: 20 });
  assert.equal(node.textContent, "");
  await act(() => root.unmount());
});

test("rolling story windows retain fully loaded history and compare timestamp instants", async () => {
  const node = document.getElementById("story-test");
  const root = createRoot(node);
  const original = slipstreamApi.story;
  slipstreamApi.story = async () => ({ ...snapshot(3, [event(1)]), total: 3, hasMore: false, nextOffset: 3 });
  const render = (sequence, items, total) => act(() => root.render(createElement(StoryFeed, {
    story: { ...snapshot(sequence, items), total, hasMore: true }, mode: "replay",
  })));
  try {
    await render(3, [event(2), event(3)], 3);
    await act(async () => node.querySelector(".story-earlier").click());
    assert.equal(node.querySelectorAll(".story-item").length, 3);
    assert.equal(node.querySelector(".story-earlier"), null);
    await render(4, [event(3), event(4, { availableAt: "2026-07-26T13:02:00Z" })], 4);
    assert.equal(node.querySelectorAll(".story-item").length, 4);
    assert.match(node.querySelector(".story-item").textContent, /Pass 4/);
    assert.match(node.textContent, /Pass 2/);
    assert.equal(node.querySelector(".story-earlier"), null);
    // A skipped/coalesced window remains discoverable even after an earlier
    // request exhausted history at its own cursor.
    await render(8, [event(7), event(8)], 8);
    assert.ok(node.querySelector(".story-earlier"));
  } finally {
    slipstreamApi.story = original;
    await act(() => root.unmount());
  }
});

test("the first event after an empty ledger is fresh for the same selected session", async () => {
  const node = document.getElementById("story-test");
  const root = createRoot(node);
  for (const Component of [StoryFeed, StoryMoments]) {
    await act(() => root.render(createElement(Component, { story: snapshot(0, []), sessionKey: "s", mode: "replay" })));
    await act(() => root.render(createElement(Component, { story: snapshot(1, [event(1)]), sessionKey: "s", mode: "replay" })));
    assert.match(node.textContent, /Pass 1/);
    if (Component === StoryFeed) assert.equal(node.querySelectorAll(".story-is-new").length, 1);
  }
  await act(() => root.unmount());
});
