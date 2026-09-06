// Real controls against the original 190-event Qualifying recording (external input).
// node tests/browser-replay-smoke.mjs http://localhost:3344 ../output/replay-smoke
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const { chromium } = createRequire(import.meta.url)("playwright");
const base = process.argv[2] ?? "http://localhost:3344";
const output = path.resolve(process.argv[3] ?? "../output/replay-smoke");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
await context.addInitScript(() => {
  localStorage.setItem("slipstream.selected-session.v1", "11357");
  localStorage.setItem("slipstream.viewing-intent.v2", JSON.stringify({ mode: "replay", followLive: false }));
});
const page = await context.newPage();
const snapshots = [];
const commands = [];
const errors = [];
const results = { browser: browser.version(), base, checks: [] };
page.on("pageerror", (error) => errors.push(error.message));
page.on("websocket", (socket) => {
  socket.on("framereceived", ({ payload }) => {
    const frame = JSON.parse(String(payload));
    if (frame.type === "state.snapshot") snapshots.push(frame);
  });
  socket.on("framesent", ({ payload }) => commands.push(JSON.parse(String(payload))));
});
const last = () => snapshots.at(-1);
const driverCount = () => Object.keys(last()?.data.drivers ?? {}).length;
async function waitUntil(predicate) {
  const deadline = Date.now() + 10_000;
  while (!predicate() && Date.now() < deadline) await page.waitForTimeout(50);
  assert.ok(predicate(), "Expected playback snapshot before timeout");
}
try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector(".play-button")?.disabled === false);
  const metadata = snapshots[0].metadata;
  assert.equal(metadata.sessionKey, "11357");
  assert.equal(metadata.eventCount, 190, "This smoke test requires the unchanged incident recording");
  assert.equal(metadata.complete, false);
  assert.equal(driverCount(), 0, "Opening must not import later driver facts");
  await page.getByText("PARTIAL RECORDING", { exact: true }).waitFor();
  const notice = await page.locator(".replay-recording-notice").boundingBox();
  const strip = await page.locator(".session-strip").boundingBox();
  const tower = await page.locator(".timing-table").filter({ visible: true }).first().boundingBox();
  assert.ok(notice.y >= strip.y + strip.height, "Notice remains below the session header");
  assert.ok(notice.y + notice.height <= tower.y, "Notice does not cover timing rows");
  const slider = page.getByRole("slider", { name: "Replay position" });
  const box = await slider.boundingBox();
  const xAt = (seconds) => 8 + (box.width - 16) * seconds / metadata.durationSeconds;
  const y = box.height / 2;
  async function clickAt(seconds) {
    const before = snapshots.length;
    await slider.click({ position: { x: xAt(seconds), y } });
    await waitUntil(() => snapshots.length > before && !last().playback.playing
      && Math.abs((Date.parse(last().sessionTime) - Date.parse(metadata.startTime)) / 1000 - seconds) < 3);
  }
  await clickAt(590);
  assert.equal(driverCount(), 0);
  await page.screenshot({ path: path.join(output, "before-first-timing.png"), fullPage: true });
  await clickAt(800);
  assert.equal(driverCount(), 22);
  const firstTiming = JSON.stringify(last().data.drivers);
  assert.match(await page.locator("body").innerText(), /22 DRIVERS/);
  await page.screenshot({ path: path.join(output, "after-first-timing.png"), fullPage: true });
  results.checks.push("Mouse click seeks from empty interval to 22 driver rows");

  await page.mouse.move(box.x + xAt(800), box.y + y);
  await page.mouse.down();
  await page.mouse.move(box.x + xAt(590), box.y + y, { steps: 12 });
  await page.mouse.up();
  await waitUntil(() => driverCount() === 0);
  assert.equal(commands.at(-1).type, "seek");
  results.checks.push("Mouse drag backwards removes later driver facts");

  await clickAt(765);
  await page.getByRole("button", { name: "PLAY", exact: true }).click();
  await waitUntil(() => driverCount() === 22 && last().playback.playing);
  assert.deepEqual(commands.at(-1), { type: "play", speed: 10 });
  await page.getByRole("button", { name: "PAUSE", exact: true }).click();
  await waitUntil(() => !last().playback.playing);
  results.checks.push("10x playback crosses first recorded timing burst and populates the tower");

  await clickAt(1715);
  await page.getByRole("button", { name: "PLAY", exact: true }).click();
  await waitUntil(() => last().seq === 190 && !last().playback.playing);
  assert.equal(driverCount(), 22);
  assert.notEqual(JSON.stringify(last().data.drivers), firstTiming, "Later recorded timing changes driver state");
  assert.equal(Date.parse(last().sessionTime), Date.parse(metadata.endTime));
  assert.ok(await page.getByText("PARTIAL RECORDING", { exact: true }).isVisible());
  results.checks.push("10x playback applies final timing burst and stops at recorded end");
  assert.deepEqual(errors, []);
  await writeFile(path.join(output, "results.json"), JSON.stringify({ ...results, errors, commands }, null, 2));
  console.log(JSON.stringify(results, null, 2));
} finally {
  await browser.close();
}
