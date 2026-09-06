// Real Chromium and server identity handshake against a disposable synthetic
// live-990001.json fixture. Never run this against application recording storage.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

const { chromium } = createRequire(import.meta.url)("playwright");
if (process.argv[2] === "--seed") {
  assert.ok(process.argv[3], "Supply a fresh disposable acceptance data directory");
  const fixture = path.resolve(process.argv[3], "live-990001.json");
  const event = (kind, occurred_at, payload) => ({ kind, occurred_at, source: "SYNTHETIC-CLOSURE-BROWSER", payload });
  const rows = [
    event("session", "2026-09-04T14:00:00Z", { key: "990001", name: "Practice 2", session_type: "Practice", session_kind: "practice", started_at: "2026-09-04T14:00:00Z", ended_at: "2026-09-04T15:00:00Z", status: "RUNNING" }),
    event("driver", "2026-09-04T14:20:00Z", { number: "44", name: "Synthetic Driver" }),
    event("timing", "2026-09-04T14:30:00Z", { number: "44", lap: 3 }),
  ];
  await writeFile(fixture, JSON.stringify(rows), { flag: "wx" });
  console.log(`Created disposable fixture: ${fixture}`);
  process.exit(0);
}
const [base, dataDirectory, outputDirectory] = process.argv.slice(2);
assert.ok(base && dataDirectory && outputDirectory, "Supply isolated server URL, disposable data directory, and output directory");
assert.ok(["127.0.0.1", "localhost"].includes(new URL(base).hostname));
const fixture = path.resolve(dataDirectory, "live-990001.json");
const rows = JSON.parse(await readFile(fixture, "utf8"));
assert.ok(rows.length === 3 && rows.every((event) => event.source === "SYNTHETIC-CLOSURE-BROWSER"));
const output = path.resolve(outputDirectory);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await context.addInitScript(() => {
  localStorage.setItem("slipstream.selected-session.v1", "990001");
  localStorage.setItem("slipstream.viewing-intent.v2", JSON.stringify({ mode: "replay", followLive: false }));
  window.__closureSockets = [];
  const Original = window.WebSocket;
  window.WebSocket = class extends Original {
    constructor(...args) { super(...args); window.__closureSockets.push(this); }
  };
});
const page = await context.newPage();
const connections = [], snapshots = [], rest = [], errors = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("websocket", (socket) => {
  connections.push(socket.url());
  socket.on("framereceived", ({ payload }) => {
    const frame = JSON.parse(String(payload));
    if (frame.type === "state.snapshot") snapshots.push(frame);
  });
});
page.on("response", async (response) => {
  if (new URL(response.url()).pathname === "/api/v1/state" && response.ok()) {
    rest.push({ url: response.url(), envelope: await response.json() });
  }
});
let blockRest = true, blockSockets = false;
const staleCatalog = await (await context.request.get(`${base}/api/v1/catalog`)).json();
await page.route("**/api/v1/catalog", (route) => route.fulfill({ json: staleCatalog }));
await page.route("**/api/v1/state?*", (route) => blockRest ? route.abort() : route.continue());
await page.routeWebSocket("**/api/v1/stream?*", (route) => {
  if (blockSockets) route.close();
  else route.connectToServer();
});
const last = () => snapshots.at(-1);
async function waitUntil(predicate) {
  const deadline = Date.now() + 12_000;
  while (!predicate() && Date.now() < deadline) await page.waitForTimeout(25);
  assert.ok(predicate(), "Expected version/cursor transition before timeout");
}
async function seek(sequence) {
  const count = snapshots.length;
  await page.evaluate((seq) => window.__closureSockets.at(-1).send(JSON.stringify({ type: "seek", seq })), sequence);
  await waitUntil(() => snapshots.length > count && last().seq === sequence);
}
async function replaceRecording(events) {
  await writeFile(fixture + ".tmp", JSON.stringify(events));
  await rename(fixture + ".tmp", fixture);
}
const results = { browser: browser.version(), base, checks: [] };
try {
  await page.goto(base);
  await waitUntil(() => last()?.playbackReady);
  const v1 = last().metadata.recordingVersion;
  await seek(2);
  const oldTime = last().sessionTime;
  await page.evaluate(() => window.__closureSockets.at(-1).close());
  await waitUntil(() => connections.length === 2 && last()?.metadata?.recordingVersion === v1 && last()?.seq === 2);
  assert.equal(new URL(connections.at(-1)).searchParams.get("recording_version"), v1);
  assert.equal(last().sessionTime, oldTime);
  results.checks.push({ name: "unchanged recording resumes the same cursor", version: v1, sequence: 2 });

  const earlier = { ...rows[1], occurred_at: "2026-09-04T14:01:00Z" };
  await replaceRecording([rows[0], earlier, ...rows.slice(1)]);
  const beforeReplacement = snapshots.length;
  await page.evaluate(() => window.__closureSockets.at(-1).close());
  await waitUntil(() => snapshots.length > beforeReplacement && last()?.metadata?.recordingVersion !== v1);
  const v2 = last().metadata.recordingVersion;
  assert.equal(new URL(connections.at(-1)).searchParams.get("recording_version"), v1);
  assert.equal(last().seq, 1);
  assert.equal(Date.parse(last().sessionTime), Date.parse(last().metadata.startTime));
  const openingConnections = connections.length;
  await page.waitForTimeout(1200);
  assert.equal(connections.length, openingConnections, "Server mismatch reset must not require another reconnect");
  results.checks.push({ name: "replacement resets in one WebSocket opening before catalog poll", requestedVersion: v1, actualVersion: v2, sequence: last().seq });

  await seek(3);
  await replaceRecording([rows[0], { ...earlier, occurred_at: "2026-09-04T14:00:30Z" }, earlier, ...rows.slice(1)]);
  blockSockets = true;
  blockRest = false;
  await page.evaluate(() => window.__closureSockets.at(-1).close());
  await waitUntil(() => rest.some((item) => item.envelope.metadata?.recordingVersion !== v2));
  const recovered = rest.at(-1);
  assert.equal(new URL(recovered.url).searchParams.get("recording_version"), v2);
  assert.equal(new URL(recovered.url).searchParams.get("seq"), "3");
  assert.equal(recovered.envelope.seq, 1);
  assert.equal(Date.parse(recovered.envelope.sessionTime), Date.parse(recovered.envelope.metadata.startTime));
  assert.ok(await page.getByRole("button", { name: "PLAY", exact: true }).isDisabled());
  results.checks.push({ name: "REST fallback resets foreign cursor with coherent metadata", requestedVersion: v2, actualVersion: recovered.envelope.metadata.recordingVersion, sequence: recovered.envelope.seq });
  blockSockets = false;
  await waitUntil(() => last()?.metadata?.recordingVersion === recovered.envelope.metadata.recordingVersion);
  await page.waitForFunction(() => document.querySelector(".play-button")?.disabled === false);
  assert.equal(last().seq, 1);
  assert.deepEqual(errors, []);
  await page.screenshot({ path: path.join(output, "recovered-replacement.png"), fullPage: true });
} catch (error) {
  results.failure = error.stack;
  await page.screenshot({ path: path.join(output, "failure.png"), fullPage: true });
  throw error;
} finally {
  results.connections = connections;
  results.errors = errors;
  await writeFile(path.join(output, "results.json"), JSON.stringify(results, null, 2));
  await browser.close();
}
console.log(JSON.stringify(results, null, 2));
