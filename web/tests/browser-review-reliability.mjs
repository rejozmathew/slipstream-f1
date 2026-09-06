// Uses the real local download/open acceptance server with disposable data.
// HTTP polling is controlled to reproduce publication between observations;
// publication, WebSocket snapshots and rendered controls use the actual app.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const { chromium } = createRequire(import.meta.url)("playwright");
const base = process.argv[2] ?? "http://127.0.0.1:18350";
const output = path.resolve(process.argv[3] ?? "../output/playwright/review-reliability");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];

async function scenario(kind) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.addInitScript(() => {
    localStorage.setItem("slipstream.selected-session.v1", "11307");
    localStorage.setItem("slipstream.viewing-intent.v2", JSON.stringify({ mode: "replay", followLive: false }));
  });
  const page = await context.newPage();
  const errors = [];
  const connections = [];
  const frames = [];
  const observedJobs = [];
  const downloadResponses = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("websocket", (socket) => {
    connections.push(socket.url());
    socket.on("framereceived", ({ payload }) => {
      const frame = JSON.parse(String(payload));
      if (frame.type === "state.snapshot") frames.push(frame);
    });
  });
  page.on("response", async (response) => {
    if (response.url().includes("/api/v1/download")) downloadResponses.push(await response.json());
  });
  let allowJobs = false;
  let allowCatalog = false;
  const initialCatalog = await (await context.request.get(`${base}/api/v1/catalog`)).json();
  assert.equal(initialCatalog.sessions.find((item) => item.sessionKey === "11307").available, false);
  await page.route("**/api/v1/catalog", async (route) => {
    if (allowCatalog) await route.continue();
    else await route.fulfill({ json: initialCatalog });
  });
  await page.route("**/api/v1/jobs", async (route) => {
    const data = allowJobs ? await (await route.fetch()).json() : { v: 1, jobs: [] };
    observedJobs.push(...data.jobs.map((item) => item.status));
    await route.fulfill({ json: data });
  });
  const last = () => frames.at(-1);
  async function waitUntil(predicate) {
    const deadline = Date.now() + 15_000;
    while (!predicate() && Date.now() < deadline) await page.waitForTimeout(50);
    assert.ok(predicate(), `Timed out in ${kind}`);
  }
  try {
    await page.goto(base);
    await waitUntil(() => last()?.metadata?.available === false);
    assert.equal(last().seq, 2);
    assert.ok(await page.getByRole("button", { name: "PLAY", exact: true }).isDisabled());
    const queued = await context.request.post(`${base}/api/v1/download?session_key=11307`);
    assert.equal(queued.status(), 202);
    let published = false;
    for (let attempt = 0; attempt < 100 && !published; attempt++) {
      const jobs = await (await context.request.get(`${base}/api/v1/jobs`)).json();
      published = jobs.jobs.some((item) => item.sessionKey === "11307" && item.status === "AVAILABLE");
      if (!published) await page.waitForTimeout(50);
    }
    assert.ok(published, "The external request must finish publishing before the browser observes it");
    if (kind === "first-seen-available") {
      allowJobs = true;
    } else {
      await page.locator(".replay-library summary").click();
      await page.getByRole("button", { name: "DOWNLOAD REPLAY", exact: true }).click();
      await waitUntil(() => downloadResponses.length > 0);
      assert.equal(downloadResponses[0].status, "AVAILABLE");
    }
    await waitUntil(() => last()?.metadata?.available === true);
    const opened = last();
    assert.equal(connections.length, 2);
    assert.equal(new URL(connections.at(-1)).searchParams.get("seq"), null);
    assert.equal(Date.parse(opened.sessionTime), Date.parse(opened.metadata.startTime));
    const play = page.getByRole("button", { name: "PLAY", exact: true });
    await play.click();
    await waitUntil(() => last()?.playback?.playing && last().seq > opened.seq);
    const elapsed = Number(await page.getByRole("slider", { name: "Replay position" }).inputValue());
    assert.ok(elapsed > 0);
    assert.equal(Object.keys(last().data.drivers).length, 22);
    await page.getByRole("button", { name: "PAUSE", exact: true }).click();
    await waitUntil(() => !last()?.playback?.playing);
    allowCatalog = true;
    allowJobs = true;
    await page.waitForFunction(() => !document.querySelector(".replay-library summary")?.textContent.includes("NOT DOWNLOADED"), { timeout: 20_000 });
    await page.waitForTimeout(2200);
    assert.equal(connections.length, 2, "Repeated AVAILABLE polls must not reopen the recording");
    if (kind === "first-seen-available") assert.ok(observedJobs.every((status) => status === "AVAILABLE"));
    assert.deepEqual(errors, []);
    if (await page.locator(".replay-library").getAttribute("open") !== null) await page.locator(".replay-library summary").click();
    await page.screenshot({ path: path.join(output, `${kind}.png`), fullPage: true });
    results.push({ kind, connections, observedJobs, downloadResponses, openingTime: opened.sessionTime, recordingVersion: opened.metadata.recordingVersion, elapsed, errors });
  } finally {
    await context.close();
  }
}

try {
  await scenario("first-seen-available");
  const cleanup = await browser.newContext();
  const response = await cleanup.request.delete(`${base}/api/v1/replay?session_key=11307`);
  assert.equal(response.status(), 200, "Delete only the disposable acceptance server's recording");
  await cleanup.close();
  await scenario("immediate-post-available");
  await writeFile(path.join(output, "results.json"), JSON.stringify({ browser: browser.version(), results }, null, 2));
  console.log(JSON.stringify({ browser: browser.version(), results }, null, 2));
} finally {
  await browser.close();
}
