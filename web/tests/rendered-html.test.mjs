import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

async function builtApplication() {
  const index = await readFile(new URL("../dist/index.html", import.meta.url), "utf8");
  const assetsDirectory = new URL("../dist/assets/", import.meta.url);
  const assetNames = await readdir(assetsDirectory);
  const javascript = await Promise.all(
    assetNames
      .filter((name) => name.endsWith(".js"))
      .map((name) => readFile(new URL(name, assetsDirectory), "utf8")),
  );
  return { index, bundle: javascript.join("\n") };
}

test("builds the Slipstream replay pit wall as static files", async () => {
  const { index, bundle } = await builtApplication();

  assert.match(index, /<title>Slipstream F1 .* Replay Pit Wall<\/title>/i);
  assert.match(index, /<div id="root"><\/div>/);
  assert.match(index, /\/assets\/.*\.js/);
  assert.match(bundle, /Timing tower/);
  assert.match(bundle, /Choose a season, weekend, and session/);
  assert.match(bundle, /SESSION TIMELINE/);
  assert.match(bundle, /Track conditions/);
  assert.match(bundle, /TRACK LOCAL TIME/);
  assert.match(bundle, /Canonical RaceState v1/);
  assert.doesNotMatch(index + bundle, /codex-preview|react-loading-skeleton|Building your site/);
});

test("uses the same-origin versioned API without a web server runtime", async () => {
  const [page, packageJson, viteConfig] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
    readFile(new URL("../vite.config.ts", import.meta.url), "utf8"),
  ]);

  assert.match(page, /api\/v1\/state/);
  assert.match(page, /api\/v1\/stream/);
  assert.match(page, /api\/v1\/replay/);
  assert.match(page, /api\/v1\/catalog/);
  assert.match(page, /new WebSocket/);
  assert.match(page, /VITE_SLIPSTREAM_API/);
  assert.match(page, /DOWNLOAD REPLAY/);
  assert.match(viteConfig, /target: "http:\/\/127\.0\.0\.1:8000"/);
  assert.match(packageJson, /"build": "vite build"/);
  assert.doesNotMatch(packageJson, /vinext|wrangler|cloudflare|next/);
});
