import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the Slipstream replay pit wall", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Slipstream F1 .* Replay Pit Wall<\/title>/i);
  assert.match(html, /Timing tower/);
  assert.match(html, /Choose a season, weekend, and session/);
  assert.match(html, /FROM START/);
  assert.match(html, /PLAY/);
  assert.match(html, /−30 SEC/);
  assert.match(html, /SESSION TIMELINE/);
  assert.match(html, /DATE/);
  assert.match(html, /Marina Bay Street Circuit/);
  assert.match(html, /EXACT OUTLINE/);
  assert.match(html, /Cars: timing-derived/);
  assert.match(html, /Replay controls/);
  assert.match(html, /Track conditions/);
  assert.match(html, /TRACK LOCAL TIME/);
  assert.match(html, /Rain sensor status only/);
  assert.match(html, /Canonical RaceState v1/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Building your site/);
});

test("starter preview code and dependency are removed", async () => {
  const [page, layout, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.match(page, /api\/v1\/state/);
  assert.match(page, /api\/v1\/stream/);
  assert.match(page, /api\/v1\/replay/);
  assert.match(page, /api\/v1\/catalog/);
  assert.match(page, /new WebSocket/);
  assert.match(page, /buildTrackGeometry/);
  assert.match(page, /circuit-svg/);
  assert.match(page, /SESSION NOT DOWNLOADED/);
  assert.match(page, /LIVE SESSION/);
  assert.match(page, /source X\/Y/);
  assert.match(page, /enhanced\/authenticated position source/);
  assert.match(page, /NOT DOWNLOADED/);
  assert.match(page, /Seconds behind live data/);
  assert.match(page, /Replay synchronized/);
  assert.match(page, /DOWNLOAD REPLAY/);
  assert.match(page, /api\/v1\/download/);
  assert.match(page, /TV SYNC/);
  assert.match(page, /SEC BEHIND/);
  assert.doesNotMatch(page, /<option value="30">30 SEC<\/option>/);
  assert.doesNotMatch(page, /track-loop/);
  assert.doesNotMatch(page, /[+−]1 EVENT/);
  assert.match(layout, /Slipstream F1/);
  assert.match(packageJson, /slipstream-f1-web/);
  assert.doesNotMatch(page + layout + packageJson, /_sites-preview|react-loading-skeleton/);
});
