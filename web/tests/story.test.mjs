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
const { StoryMoments, StoryMomentCard } = await server.ssrLoadModule("/components/story/StoryMoments.tsx");
const { StoryTicker } = await server.ssrLoadModule("/components/story/StoryTicker.tsx");
const { StoryMomentQueue } = await server.ssrLoadModule("/components/story/momentQueue.ts");
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
  assert.match(node.textContent, /once the session is recorded/);
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

const drivers = {
  "1": { number: "1", code: "NOR", name: "Lando NORRIS", team_colour: "FF8700", position: 1, lap: 70, classification: "FINISHED", gap_to_leader: "LEADER" },
  "2": { number: "2", code: "ANT", name: "Kimi ANTONELLI", team_colour: "00D2BE", position: 2, lap: 70, classification: null, gap_to_leader: "+3.100" },
  "3": { number: "3", code: "PIA", name: "Oscar PIASTRI", team_colour: "FF8700", position: 3, lap: 70, classification: "FINISHED", gap_to_leader: "+6.250" },
};
const session = { key: "s", layout_family: "race", lap: 70, total_laps: 70, gmt_offset: "+02:00", meeting_name: "Hungarian Grand Prix" };

test("feed uses the authored time/tag/text columns, cause tones, driver chips and knowledge lag", async () => {
  const node = document.getElementById("story-test");
  const root = createRoot(node);
  try {
    await act(() => root.render(createElement(StoryFeed, { mode: "replay", drivers, session, onReplay: () => {}, story: snapshot(4, [
      event(1, { kind: "RACE_CONTROL", priority: 1, title: "Routine notice" }),
      event(2, { kind: "PIT_IN", cause: "PIT", priority: 2 }),
      event(3, { kind: "BATTLE", priority: 2, lap: 66 }),
      event(4, { data: { position: 1 } }),
    ]) })));
    const rows = node.querySelectorAll(".fd-item");
    assert.equal(rows.length, 3, "Highlights is the authored default");
    assert.equal(node.querySelectorAll('.story-filters button[aria-pressed="true"]')[0].textContent, "HIGHLIGHTS");
    assert.ok(rows[0].classList.contains("tone-gain"));
    assert.ok(rows[0].classList.contains("is-hl"));
    const columns = [...rows[0].querySelector(".story-inspect").children];
    assert.deepEqual(columns.map(column => column.className.split(" ")[0]), ["story-time", "story-tag", "story-body"]);
    assert.match(columns[1].textContent, /NEW LEADER/);
    assert.match(columns[2].textContent, /Norris passes Antonelli/);
    assert.ok(rows[1].classList.contains("is-past"));
    assert.match(rows[1].textContent, /EARLIER/);
    assert.ok(rows[2].classList.contains("tone-pit"));
    await act(() => columns[0].closest("button").click());
    assert.match(rows[0].textContent, /15:01:00.*15:01:05 · 5 s later/);
    assert.deepEqual([...rows[0].querySelectorAll(".fd-drv")].map(chip => chip.textContent), ["NOR", "ANT"]);
    assert.equal(rows[0].querySelector(".fd-drv").style.getPropertyValue("--team"), "#FF8700");
    assert.match(rows[0].querySelector(".story-replay").textContent, /REPLAY FROM L12/);
    await act(() => [...node.querySelectorAll(".story-filters button")].find(button => button.textContent === "EVERYTHING").click());
    assert.equal(node.querySelectorAll(".fd-item").length, 4);
    assert.equal(node.querySelectorAll(".is-new").length, 0, "Changing a filter is not news");
  } finally { await act(() => root.unmount()); }
});

test("typed moment compositions preserve flag identity, team lead cards and cursor-known result gaps", async () => {
  const node = document.getElementById("story-test");
  const root = createRoot(node);
  const render = (extra, people = drivers) => act(() => root.render(createElement(StoryMomentCard, { event: event(10, extra), drivers: people, session })));
  try {
    await render({ kind: "FLAG", cause: "VSC", driverNumbers: [], data: { flag: "VSC" }, title: "Virtual Safety Car", detail: "deployed" });
    assert.ok(node.querySelector(".to--flag.to-flag--vsc .to-flagbox"));
    assert.equal(node.querySelector(".to-slab"), null);
    for (const [flag, title] of [["SAFETY_CAR", "Safety Car"], ["RED_FLAG", "Session suspended"], ["RED", "Session suspended"], ["CHEQUERED", "Chequered flag"]]) {
      await render({ kind: "FLAG", cause: flag, driverNumbers: [], data: { flag }, title: flag, detail: "Official whole-track status" });
      assert.ok(node.querySelector(`.to-flag--${flag.toLowerCase()} .to-flagbox`));
      assert.equal(node.querySelector(".to-flagbox strong").textContent, title);
    }
    await render({ data: { position: 1 } });
    assert.ok(node.querySelector(".to--lead_change .to-slab"));
    assert.equal(node.querySelector(".to-first").textContent, "Lando");
    assert.deepEqual([...node.querySelectorAll(".to-drv small")].map(chip => chip.textContent), ["P1", "P2"]);
    await render({ kind: "STOPPED", cause: "STOPPED", driverNumbers: ["2"], title: "ANT stopped" });
    assert.ok(node.querySelector(".to--stopped .to-slab"));
    await render({ kind: "RESULT", state: "provisional", driverNumbers: ["1"], title: "NOR wins on the road" });
    assert.equal(node.querySelectorAll(".to-pod").length, 3);
    assert.match(node.textContent, /PROVISIONAL/);
    assert.match(node.querySelector(".to-pod--2").textContent, /ON FINAL LAP/);
    assert.doesNotMatch(node.querySelector(".to-pod--2").textContent, /3\.100/);
    assert.match(node.querySelector(".to-pod--3").textContent, /6\.250/);
    await render({ kind: "RESULT", driverNumbers: ["1"] }, { "1": drivers[1], "3": drivers[3] });
    assert.equal(node.querySelector(".to-pod--2"), null, "Missing P2 is not invented from a P3 row");
    assert.ok(node.querySelector(".to-pod--3"));
    await render({ kind: "POLE", driverNumbers: ["1"], data: { lapTime: 82.718, top: ["1", "2"] } });
    assert.match(node.querySelector(".to--pole").textContent, /POLE POSITION.*1:22\.718.*NORPOLE.*ANTP2/);
    await render({ kind: "ELIMINATED", phase: "Q1", driverNumbers: ["2", "3"] });
    assert.match(node.querySelector(".to--eliminated").textContent, /OUT IN Q1.*2 drivers eliminated/);
    assert.equal(node.querySelectorAll(".to--eliminated .to-drv").length, 2);
    await render({ kind: "SESSION_END", driverNumbers: [], title: "Q1 flag shown", detail: "Laps in progress may change the order." });
    assert.doesNotMatch(node.textContent, /fastest/);
    assert.match(node.textContent, /Laps in progress/);
    await render({ kind: "PHASE", phase: "Q2", title: "Q2 begins", detail: "Source-confirmed segment change" });
    assert.match(node.querySelector(".to--phase").textContent, /SEGMENT CHANGE.*Q2 begins/);
  } finally { await act(() => root.unmount()); }
});

test("takeovers hold explanations, replace matching types, bound the queue and coalesce by rank", () => {
  const queue = new StoryMomentQueue();
  const flag = event(1, { kind: "FLAG", cause: "VSC", data: { flag: "VSC" } });
  const stopped = event(2, { kind: "STOPPED", cause: "STOPPED" });
  queue.offer([flag], 1, 0);
  assert.equal(queue.current.hold, 4200);
  assert.equal(queue.current.minHold, 2600);
  queue.offer([stopped], 1, 1000);
  assert.equal(queue.current.event.id, "1");
  queue.advance(2599);
  assert.equal(queue.current.event.id, "1");
  queue.advance(2600);
  assert.equal(queue.current.event.id, "2");
  assert.equal(queue.current.hold, 5600);
  queue.offer([event(3, { kind: "STOPPED" })], 1, 2700);
  assert.equal(queue.current.event.id, "3", "A newer explanation of the same kind supersedes it");
  queue.offer([flag, event(4, { kind: "PHASE" }), event(5, { kind: "ELIMINATED" }), event(6, { kind: "SESSION_END" })], 1, 2800);
  assert.equal(queue.pending.length, 3);
  assert.deepEqual(queue.pending.map(item => item.id), ["4", "5", "6"]);
  queue.clear();
  queue.offer([stopped, event(7, { kind: "RESULT" }), event(8, { kind: "PHASE" })], 5, 5000);
  assert.equal(queue.current.event.id, "7", "Result rank survives a burst of lower-priority explanations");
  assert.equal(queue.current.hold, 5400);
  assert.equal(queue.current.minHold, 1560);
  assert.equal(queue.pending.length, 0);
  queue.advance(10400);
  assert.equal(queue.current, null);
  queue.offer([flag, stopped, event(9, { kind: "FLAG", data: { flag: "RED_FLAG" } })], 20, 11000);
  assert.equal(queue.current.event.id, "9");
  assert.equal(queue.pending.length, 0);
});

test("ticker keeps four newest highlights, excludes battle, exposes detail and inspects without replay", async () => {
  const node = document.getElementById("story-test");
  const root = createRoot(node);
  const inspected = [];
  const items = [event(1), event(2), event(3), event(4), event(5, { kind: "BATTLE" }), event(6, { priority: 1 }), event(7), event(8, { availableAt: "2026-07-26T13:03:00Z" })];
  const render = (sequence, events, generation = 0) => act(() => root.render(createElement(StoryTicker, { mode: "replay", story: snapshot(sequence, events), sessionKey: "s", generation, drivers, session, onInspect: item => inspected.push(item.id) })));
  try {
    await render(8, items);
    assert.equal(node.querySelectorAll(".tk-item").length, 4);
    assert.deepEqual([...node.querySelectorAll(".tk-item b")].map(item => item.textContent), ["Pass 7", "Pass 4", "Pass 3", "Pass 2"]);
    assert.equal(node.querySelectorAll(".is-new").length, 0);
    assert.match(node.querySelector(".is-latest em").textContent, /Confirmed after both cars/);
    assert.equal(node.querySelector(".is-latest").style.getPropertyValue("--team"), "#FF8700");
    await act(() => node.querySelector(".tk-inspect").click());
    assert.deepEqual(inspected, ["7"]);
    await render(9, [...items, event(9, { supersedes: "7" })]);
    assert.equal(node.querySelectorAll(".is-new").length, 1);
    assert.doesNotMatch(node.textContent, /Pass 7/);
    await render(20, [event(20)], 1);
    assert.equal(node.querySelectorAll(".is-new").length, 0);
  } finally { await act(() => root.unmount()); }
});

test("moment presentation ignores future availability and a hidden reveal is quiet", async () => {
  const node = document.getElementById("story-test");
  const root = createRoot(node);
  const render = (story, visible = true, version = "1") => act(() => root.render(createElement(StoryMoments, { mode: "replay", story, sessionKey: "s", visible, recordingVersion: version })));
  try {
    await render(snapshot(1, []));
    await render(snapshot(2, [event(2, { availableAt: "2026-07-26T13:03:00Z" })]));
    assert.equal(node.querySelector(".story-moment"), null);
    await render(snapshot(3, [event(3)]), false);
    await render(snapshot(4, [event(3), event(4)]), true);
    assert.equal(node.querySelector(".story-moment"), null);
    await render(snapshot(5, [event(5)]), true);
    assert.match(node.textContent, /Pass 5/);
    await render(snapshot(6, [event(6)]), true, "2");
    assert.equal(node.querySelector(".story-moment"), null, "A replacement recording is navigation");
  } finally { await act(() => root.unmount()); }
});
