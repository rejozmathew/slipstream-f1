// Standalone real Chromium acceptance. Requires an isolated harness server and Playwright.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const { chromium } = createRequire(import.meta.url)("playwright");
const base = process.argv[2] ?? "http://127.0.0.1:18346";
const output = path.resolve(process.argv[3] ?? "../output/playwright");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
const page = await context.newPage();
const snapshots = [];
const errors = [];
const results = { browser: browser.version(), base, checks: [] };
page.on("pageerror", (error) => errors.push(error.message));
page.on("websocket", (ws) => ws.on("framereceived", ({ payload }) => {
  try {
    const frame = JSON.parse(String(payload));
    if (frame.type === "state.snapshot") snapshots.push(frame);
  } catch { /* Non-application control frames are irrelevant. */ }
}));
await context.addInitScript(() => {
  window.__acceptanceSockets = [];
  const Original = window.WebSocket;
  window.WebSocket = class extends Original {
    constructor(...args) { super(...args); window.__acceptanceSockets.push(this); }
  };
});
const last = () => snapshots.at(-1);
async function waitForSnapshotTime(at) {
  for (let attempt = 0; attempt < 100 && Date.parse(last()?.sessionTime) !== Date.parse(at); attempt++) await page.waitForTimeout(50);
  assert.equal(Date.parse(last()?.sessionTime), Date.parse(at));
}
async function seek(at) {
  const before = snapshots.length;
  await page.evaluate((target) => window.__acceptanceSockets.at(-1).send(JSON.stringify({ type: "seek", at: target })), at);
  await page.waitForFunction(() => true);
  for (let attempt = 0; attempt < 100 && snapshots.length === before; attempt++) await page.waitForTimeout(50);
  assert.ok(snapshots.length > before);
  assert.equal(Date.parse(last().sessionTime), Date.parse(at));
}
try {
  await page.goto(base);
  await page.evaluate(() => {
    localStorage.setItem("slipstream.selected-session.v1", "11357");
    localStorage.setItem("slipstream.viewing-intent.v2", JSON.stringify({ mode: "replay", followLive: false }));
  });
  snapshots.length = 0;
  await page.reload();
  await page.getByRole("button", { name: "PLAY", exact: true }).waitFor();
  await page.waitForFunction(() => !document.querySelector(".play-button")?.disabled);
  assert.equal(last().data.session.key, "11357");
  assert.equal(Object.keys(snapshots[0].data.drivers).length, 0, "No final-state flash at the official start");
  await seek("2026-09-05T14:05:08Z");
  assert.equal(Object.keys(last().data.drivers).length, 0);
  await seek("2026-09-05T14:13:20Z");
  assert.equal(Object.keys(last().data.drivers).length, 22);
  assert.equal(Object.values(last().data.drivers).filter((driver) => driver.best_lap).length, 22);
  await page.screenshot({ path: path.join(output, "qualifying-141320.png"), fullPage: true });
  await writeFile(path.join(output, "qualifying-dom.txt"), await page.locator("body").innerText());
  results.checks.push({ name: "C01 original Qualifying at exact cursors", status: "PASS", drivers: 22, sequence: last().seq });
  // Exercise the actual controls after proving the exact evidence cursor.
  await page.getByRole("slider", { name: "Replay position" }).press("ArrowRight");
  await page.waitForFunction(() => document.querySelector('[aria-label="Replay position"]').value === "801");
  await waitForSnapshotTime("2026-09-05T14:13:21Z");
  await page.getByRole("button", { name: "+30s", exact: true }).click();
  await page.waitForFunction(() => document.querySelector('[aria-label="Replay position"]').value === "831");
  await waitForSnapshotTime("2026-09-05T14:13:51Z");
  results.checks.push({ name: "Replay slider keyboard and relative-seek button", status: "PASS" });

  // Fail both initial transports long enough for a successful catalog poll.
  let blockConnections = true;
  let failedRest = 0;
  let catalogResponses = 0;
  page.on("response", (response) => { if (response.url().includes("/api/v1/catalog") && response.status() === 200) catalogResponses++; });
  await page.route("**/api/v1/state?*", async (route) => {
    if (blockConnections) {
      failedRest++;
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "SYNTHETIC initial timing failure" }) });
    } else await route.continue();
  });
  await page.routeWebSocket("**/api/v1/stream?*", (socket) => {
    if (blockConnections) socket.close({ code: 1013, reason: "SYNTHETIC opening failure" });
    else socket.connectToServer();
  });
  await page.reload();
  await page.getByText("SLIPSTREAM DATA UNAVAILABLE", { exact: true }).waitFor();
  await page.waitForTimeout(16_000);
  assert.ok(catalogResponses >= 2, "Catalog polling must actually have succeeded during failed timing");
  assert.ok(failedRest >= 1);
  assert.ok(await page.getByText("SLIPSTREAM DATA UNAVAILABLE", { exact: true }).isVisible());
  assert.ok(await page.getByRole("button", { name: "PLAY", exact: true }).isDisabled());
  await page.screenshot({ path: path.join(output, "retrying-after-catalog-success.png"), fullPage: true });
  blockConnections = false;
  await page.waitForFunction(() => !document.querySelector(".play-button")?.disabled, { timeout: 20_000 });
  assert.equal(await page.getByText("SLIPSTREAM DATA UNAVAILABLE", { exact: true }).count(), 0);
  assert.equal(Object.keys(last().data.drivers).length, 0);
  results.checks.push({ name: "C07 initial REST and WebSocket failure, catalog cannot conceal failure, automatic recovery", status: "PASS", failedRest, catalogResponses });

  // A disconnect keeps the already proven timing visible and resumes its cursor.
  await seek("2026-09-05T14:13:20Z");
  const savedCursor = last().seq;
  blockConnections = true;
  await page.evaluate(() => window.__acceptanceSockets.at(-1).close());
  await page.getByText("SLIPSTREAM DATA UNAVAILABLE", { exact: true }).waitFor();
  assert.ok((await page.locator("body").innerText()).includes("22 DRIVERS"));
  assert.ok(await page.getByRole("button", { name: "PLAY", exact: true }).isDisabled());
  blockConnections = false;
  await page.waitForFunction(() => !document.querySelector(".play-button")?.disabled);
  assert.equal(last().seq, savedCursor);
  results.checks.push({ name: "C07 valid timing survives disconnect and cursor resumes", status: "PASS" });

  // Deliberate replay survives refresh while the live source remains eligible.
  await page.reload();
  await page.waitForFunction(() => !document.querySelector(".play-button")?.disabled);
  assert.equal(last().data.session.key, "11357");
  assert.ok((await page.locator("body").innerText()).includes("Qualifying - REPLAY"));
  const liveButton = page.getByRole("button", { name: "GO LIVE", exact: true }).filter({ visible: true });
  await liveButton.first().click();
  await page.getByLabel("Live sync controls").waitFor();
  await page.reload();
  await page.getByLabel("Live sync controls").waitFor();
  assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem("slipstream.viewing-intent.v2")).followLive), true);
  const alias = await context.newPage();
  await alias.goto(base.replace("127.0.0.1", "localhost"));
  await alias.getByLabel("Live sync controls").waitFor();
  assert.equal(await alias.evaluate(() => localStorage.getItem("slipstream.viewing-intent.v2")), null);
  await alias.close();
  results.checks.push({ name: "C14 deliberate replay, follow-live persistence, separate IP/hostname storage", status: "PASS" });

  if (process.argv.includes("--downloads")) {
    await page.request.post(base + "/__fixture/action", { data: { start: true, downloadFail: true } });
    const firstJob = await page.request.post(base + "/api/v1/download?session_key=11355");
    assert.equal(firstJob.status(), 202);
    await page.getByText("REPLAY 11355: DOWNLOADING", { exact: true }).waitFor();
    const liveBefore = last().seq;
    await page.reload();
    await page.getByText("REPLAY 11355: DOWNLOADING", { exact: true }).waitFor();
    await page.request.post(base + "/api/v1/download?session_key=11355");
    await page.getByText("REPLAY 11355: FAILED", { exact: true }).waitFor();
    assert.equal((await (await page.request.get(base + "/__fixture/status")).json()).downloadCalls, 1, "Duplicate job submission must coalesce");
    assert.equal(last().data.session.key, "11357");
    assert.ok(last().seq > liveBefore, "Live viewer must continue through failed download and refresh");
    await page.screenshot({ path: path.join(output, "download-failure-during-live.png"), fullPage: true });
    await page.request.post(base + "/__fixture/action", { data: { downloadFail: false } });
    await page.request.post(base + "/api/v1/download?session_key=11355");
    await page.getByText("REPLAY 11355: DOWNLOADING", { exact: true }).waitFor();
    await page.getByText("REPLAY 11355: DOWNLOADING", { exact: true }).waitFor({ state: "detached", timeout: 15_000 });
    const jobs = (await (await page.request.get(base + "/api/v1/jobs")).json()).jobs;
    assert.equal(jobs.find((job) => job.sessionKey === "11355").status, "AVAILABLE");
    const catalog = await (await page.request.get(base + "/api/v1/catalog")).json();
    assert.equal(catalog.sessions.find((session) => session.sessionKey === "11355").available, true);
    assert.equal(last().data.session.key, "11357");
    results.checks.push({ name: "C15 download progress survives refresh, duplicate requests coalesce, failure retries, live timing continues", status: "PASS" });
  }

  await page.screenshot({ path: path.join(output, "recovered-live.png"), fullPage: true });
  results.errors = errors;
  assert.deepEqual(errors, []);
  console.log(JSON.stringify(results, null, 2));
} catch (error) {
  results.failure = error.stack;
  await page.screenshot({ path: path.join(output, "failure.png"), fullPage: true });
  throw error;
} finally {
  await writeFile(path.join(output, "browser-p0-results.json"), JSON.stringify(results, null, 2));
  await browser.close();
}
