// Start tools/download_open_acceptance.py with a fresh data directory first.
// Uses the external Barcelona 11307 recording reported in the smoke test.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const { chromium } = createRequire(import.meta.url)("playwright");
const base = process.argv[2] ?? "http://127.0.0.1:18350";
const output = path.resolve(process.argv[3] ?? "../output/download-open");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await context.addInitScript(() => {
  localStorage.setItem("slipstream.selected-session.v1", "11307");
  localStorage.setItem("slipstream.viewing-intent.v2", JSON.stringify({ mode: "replay", followLive: false }));
  window.__downloadOpenSockets = [];
  const Original = window.WebSocket;
  window.WebSocket = class extends Original {
    constructor(...args) { super(...args); window.__downloadOpenSockets.push(this); }
  };
});
const page = await context.newPage();
const connections = [];
const snapshots = [];
const commands = [];
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("websocket", (socket) => {
  connections.push(socket.url());
  socket.on("framereceived", ({ payload }) => {
    const frame = JSON.parse(String(payload));
    if (frame.type === "state.snapshot") snapshots.push(frame);
  });
  socket.on("framesent", ({ payload }) => commands.push(JSON.parse(String(payload))));
});
const last = () => snapshots.at(-1);
async function waitUntil(predicate) {
  const deadline = Date.now() + 12_000;
  while (!predicate() && Date.now() < deadline) await page.waitForTimeout(50);
  assert.ok(predicate(), "Expected download/open state before timeout");
}
try {
  await page.goto(base);
  await waitUntil(() => last()?.metadata);
  assert.equal(last().metadata.available, false, "Start with a never-downloaded session");
  assert.equal(last().seq, 2, "The placeholder cursor differs from the real recording");
  const firstConnectionCount = connections.length;
  await page.evaluate(() => window.__downloadOpenSockets.at(-1).close());
  await waitUntil(() => connections.length > firstConnectionCount && last()?.metadata?.available === false);
  assert.equal(new URL(connections.at(-1)).searchParams.get("seq"), null, "Placeholder disconnect also opens without a reusable recording cursor");
  const play = page.getByRole("button", { name: "PLAY", exact: true });
  assert.ok(await play.isDisabled());
  await page.locator(".replay-library summary").click();
  await page.getByRole("button", { name: "DOWNLOAD REPLAY", exact: true }).click();
  await page.waitForFunction(() => document.querySelector(".play-button")?.disabled === false);
  const opening = last();
  await play.click();
  await waitUntil(() => last()?.playback?.playing);
  await page.waitForTimeout(700);
  const elapsed = Number(await page.getByRole("slider", { name: "Replay position" }).inputValue());
  console.log(JSON.stringify({ connections, opening: { time: opening.sessionTime, start: opening.metadata.startTime, seq: opening.seq }, afterPlay: { time: last().sessionTime, seq: last().seq, elapsed } }));
  await page.screenshot({ path: path.join(output, "download-then-play.png"), fullPage: true });
  assert.equal(Date.parse(opening.sessionTime), Date.parse(opening.metadata.startTime), "A newly downloaded replay opens at session start");
  assert.equal(new URL(connections.at(-1)).searchParams.get("seq"), null, "Placeholder event sequence must not resume into the downloaded file");
  assert.ok(elapsed > 0, "Pressing Play immediately advances the visible timeline without seeking");
  assert.equal(Object.keys(last().data.drivers).length, 22);
  assert.ok(Object.values(last().data.drivers).every((driver) => driver.name));
  assert.deepEqual(commands, [{ type: "play", speed: 10 }], "No seek/reset workaround before playback");
  await page.getByRole("button", { name: "PAUSE", exact: true }).click();
  await waitUntil(() => !last().playback.playing);
  const pausedSequence = last().seq;
  const playedConnectionCount = connections.length;
  await page.evaluate(() => window.__downloadOpenSockets.at(-1).close());
  await waitUntil(() => connections.length > playedConnectionCount && last()?.metadata?.available === true);
  await page.waitForFunction(() => document.querySelector(".play-button")?.disabled === false);
  assert.equal(new URL(connections.at(-1)).searchParams.get("seq"), String(pausedSequence), "Same-recording reconnect retains its actual event cursor");
  assert.equal(last().seq, pausedSequence);
  assert.deepEqual(errors, []);
  await writeFile(path.join(output, "results.json"), JSON.stringify({ browser: browser.version(), connections, openingTime: opening.sessionTime, elapsed, drivers: 22, resumedSequence: pausedSequence, errors }, null, 2));
} finally {
  await browser.close();
}
