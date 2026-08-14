import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

async function builtApplication() {
  const index = await readFile(new URL("../dist/index.html", import.meta.url), "utf8");
  const assetsDirectory = new URL("../dist/assets/", import.meta.url);
  const assetNames = await readdir(assetsDirectory);
  const javascript = await Promise.all(
    assetNames.filter((name) => name.endsWith(".js")).map((name) => readFile(new URL(name, assetsDirectory), "utf8")),
  );
  return { index, bundle: javascript.join("\n") };
}

test("builds the replay-driven desktop shell as static files", async () => {
  const { index, bundle } = await builtApplication();

  assert.match(index, /<title>Slipstream F1 .* Replay Pit Wall<\/title>/i);
  assert.match(index, /<div id="root"><\/div>/);
  assert.match(index, /\/assets\/.*\.js/);
  assert.match(bundle, /Timing tower/);
  assert.match(bundle, /SEASON/);
  assert.match(bundle, /WEEKEND/);
  assert.match(bundle, /SESSION/);
  assert.match(bundle, /BALANCED/);
  assert.match(bundle, /TIMING FOCUS/);
  assert.match(bundle, /STRATEGY FOCUS/);
  assert.match(bundle, /No sample race has been substituted/);
  assert.match(bundle, /PHASE - UNKNOWN/);
  assert.match(bundle, /ANALYTICS - NOT ENABLED/);
  assert.match(bundle, /TV SYNC/);
  assert.doesNotMatch(bundle, /Carlos Sainz|Singapore Grand Prix/);
  assert.doesNotMatch(index + bundle, /codex-preview|react-loading-skeleton|Building your site/);
});

test("keeps versioned API and WebSocket transport in typed clients", async () => {
  const [apiClient, socketClient, page, packageJson, viteConfig, replayControls, replayLibrary, sessionHook] = await Promise.all([
    readFile(new URL("../api/client.ts", import.meta.url), "utf8"),
    readFile(new URL("../api/replaySocket.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
    readFile(new URL("../vite.config.ts", import.meta.url), "utf8"),
    readFile(new URL("../components/shell/ReplayControls.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/shell/ReplayLibrary.tsx", import.meta.url), "utf8"),
    readFile(new URL("../hooks/useSlipstreamSession.ts", import.meta.url), "utf8"),
  ]);

  assert.match(apiClient, /api\/v1\/state/);
  assert.match(apiClient, /api\/v1\/stream/);
  assert.match(apiClient, /api\/v1\/replay/);
  assert.match(apiClient, /api\/v1\/catalog/);
  assert.match(apiClient, /VITE_SLIPSTREAM_API/);
  assert.match(socketClient, /new WebSocket/);
  assert.match(page, /AppShell/);
  assert.doesNotMatch(page, /sampleState|sampleDrivers/);
  assert.match(viteConfig, /target: "http:\/\/127\.0\.0\.1:8000"/);
  assert.match(packageJson, /"typecheck": "tsc --noEmit"/);
  assert.match(replayControls, /commandAvailable/);
  assert.match(replayControls, /if \(isPlaying && commandAvailable\).*type: "play"/);
  assert.match(replayControls, /type: "delay"/);
  assert.match(replayControls, /disabled={!enabled}/);
  assert.match(replayLibrary, /aria-label="Season"/);
  assert.match(replayLibrary, /aria-label="Race weekend"/);
  assert.match(replayLibrary, /aria-label="Weekend session"/);
  assert.match(sessionHook, /commandAvailable && socketRef\.current\?\.send/);
  assert.doesNotMatch(packageJson, /vinext|wrangler|cloudflare|next/);
});