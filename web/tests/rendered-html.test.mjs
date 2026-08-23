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
  assert.match(bundle, /TOWER WIDE/);
  assert.match(bundle, /ANALYSIS WIDE/);
  assert.match(bundle, /TOWER VIEW/);
  assert.match(bundle, /PIRELLI BASELINE/);
  assert.match(bundle, /RACE NOW/);
  assert.match(bundle, /PUBLISHED STRATEGY CONTEXT/);
  assert.doesNotMatch(bundle, /Strategy Outlook/);
  assert.doesNotMatch(bundle, /NET PIT LOSS/);
  assert.match(bundle, /PACE DELTA/);
  assert.match(bundle, /CHANGE DRIVER/);
  assert.match(bundle, /No sample race has been substituted/);
  assert.match(bundle, /QUALIFYING CUT LINE/);
  assert.match(bundle, /WAITING FOR PUBLIC TIMING FEED/);
  assert.match(bundle, /LIVE DELAY/);
  assert.match(bundle, /SYNC DELAY/);
  assert.doesNotMatch(bundle, /Carlos Sainz|Singapore Grand Prix/);
  assert.doesNotMatch(index + bundle, /codex-preview|react-loading-skeleton|Building your site/);
});

test("keeps versioned API and WebSocket transport in typed clients", async () => {
  const [apiClient, socketClient, page, packageJson, viteConfig, replayControls, liveControls, replayLibrary, sessionHook, raceView, preferences] = await Promise.all([
    readFile(new URL("../api/client.ts", import.meta.url), "utf8"),
    readFile(new URL("../api/replaySocket.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
    readFile(new URL("../vite.config.ts", import.meta.url), "utf8"),
    readFile(new URL("../components/shell/ReplayControls.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/shell/LiveControls.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/shell/ReplayLibrary.tsx", import.meta.url), "utf8"),
    readFile(new URL("../hooks/useSlipstreamSession.ts", import.meta.url), "utf8"),
    readFile(new URL("../views/RaceView.tsx", import.meta.url), "utf8"),
    readFile(new URL("../hooks/useProductPreferences.ts", import.meta.url), "utf8"),
  ]);

  assert.match(apiClient, /api\/v1\/state/);
  assert.match(apiClient, /api\/v1\/stream/);
  assert.match(apiClient, /api\/v1\/replay/);
  assert.match(apiClient, /api\/v1\/catalog/);
  assert.match(apiClient, /api\/v1\/analytics/);
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
  assert.match(liveControls, /\[0, 5, 10, 15, 30\]/);
  assert.match(liveControls, /RESET \/ LIVE/);
  assert.doesNotMatch(liveControls, /seek|pause|speed/);
  assert.match(replayLibrary, /aria-label="Season"/);
  assert.match(replayLibrary, /aria-label="Race weekend"/);
  assert.match(replayLibrary, /aria-label="Weekend session"/);
  assert.match(sessionHook, /commandAvailable && socketRef\.current\?\.send/);
  assert.doesNotMatch(sessionHook, /setAnalytics\(null\).*viewingMode === "live"/s);
  assert.match(raceView, /\["standard", "timing", "strategy"\]/);
  assert.match(preferences, /slipstream\.device-preferences\.v1/);
  assert.match(preferences, /includedRaceStates/);
  assert.match(preferences, /rotationIntervalSeconds/);
  assert.match(preferences, /alertOnCriticalStatus/);
  assert.doesNotMatch(packageJson, /vinext|wrangler|cloudflare|next/);
});

test("wires Strategy, Driver, Battle and navigation to canonical server contracts", async () => {
  const [strategyView, snapshot, driverView, battleView, trackMap, shell] = await Promise.all([
    readFile(new URL("../views/StrategyView.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/analysis/SessionStrategySnapshot.tsx", import.meta.url), "utf8"),
    readFile(new URL("../views/DriverFocusView.tsx", import.meta.url), "utf8"),
    readFile(new URL("../views/BattleView.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/analysis/TrackMap.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/shell/AppShell.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(strategyView, /publishedStrategy\?\.baseline/);
  assert.match(strategyView, /PirelliBaseline/);
  assert.match(strategyView, /RaceNow/);
  assert.doesNotMatch(strategyView, /dryRuleStates/);
  assert.match(snapshot, /Pirelli baseline · Race now/);
  assert.match(driverView, /model\?\.read\.headline/);
  assert.match(driverView, /focusedDriverNumbers=\{\[driverNumber\]\}/);
  assert.match(driverView, /sessionLayout === "qualifying"/);
  assert.match(driverView, /CURSOR-SAFE LAP EVIDENCE/);
  assert.match(battleView, /analytics\?\.battle\.histories/);
  assert.doesNotMatch(battleView, /stateHistory/);
  assert.match(battleView, /Published strategy context/);
  assert.match(trackMap, /car-deemphasized/);
  assert.match(shell, /layout === "race" \|\| \(view !== "strategy" && view !== "battle"\)/);
  assert.match(shell, /querySelectorAll<HTMLElement>\("\.timing-table, \.analysis-stack"\)/);
});
test("keeps Packet E TV and analytics contracts truthful", async () => {
  const [tvMode, protocol, publishedStrategy, battleCard, timingTower, strategyView] = await Promise.all([
    readFile(new URL("../views/TVModeView.tsx", import.meta.url), "utf8"),
    readFile(new URL("../domain/protocol.ts", import.meta.url), "utf8"),
    readFile(new URL("../components/analysis/PublishedStrategy.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/battle/BattleDriverCard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/timing/TimingTower.tsx", import.meta.url), "utf8"),
    readFile(new URL("../views/StrategyView.tsx", import.meta.url), "utf8"),
  ]);

  assert.doesNotMatch(tvMode, /drivers\.slice\(/);
  assert.match(tvMode, /state\.session\.display_status/);
  assert.doesNotMatch(tvMode, /statusTone\(state\.session\.track_status\)/);
  assert.match(tvMode, /focusedDriverNumbers=\{\[left\.number, right\.number\]\}/);
  assert.match(tvMode, /focusedDriverNumbers=\{\[driver\.number\]\}/);
  assert.match(tvMode, /tv-status-chequered|return "chequered"/);
  assert.match(tvMode, /qualifyingStates/);
  assert.match(tvMode, /TVQualifyingCutline/);
  assert.match(protocol, /perDriverState\?: Record<string, DryTyreRequirementState>/);
  assert.match(protocol, /status: "NOT_IMPLEMENTED"/);
  assert.match(protocol, /metrics: null/);
  assert.match(protocol, /publishedStrategy: PublishedStrategyIntelligence/);
  assert.doesNotMatch(tvMode, /UNDERCUT/);
  assert.doesNotMatch(tvMode, /STRATEGY · DISPOSITION/);
  assert.match(publishedStrategy, /ordered \? "→" : "\+"/);
  assert.match(publishedStrategy, /publishedWindowSummary/);
  for (const source of [publishedStrategy, battleCard, timingTower, strategyView, tvMode]) {
    assert.doesNotMatch(source, /windows\[0\]/);
  }
});

test("uses server-authored status and preserves same-session live replay handoff", async () => {
  const [sessionStrip, sessionHook, protocol] = await Promise.all([
    readFile(new URL("../components/shell/SessionStrip.tsx", import.meta.url), "utf8"),
    readFile(new URL("../hooks/useSlipstreamSession.ts", import.meta.url), "utf8"),
    readFile(new URL("../domain/protocol.ts", import.meta.url), "utf8"),
  ]);

  assert.match(sessionStrip, /session\.display_status/);
  assert.match(sessionStrip, /session\.display_status \?\? session\.track_status/);
  assert.match(protocol, /control_status/);
  assert.match(protocol, /marshal_status/);
  assert.match(protocol, /display_status/);
  assert.match(protocol, /handoff\?: "REPLAY_READY"/);
  assert.match(sessionHook, /envelope\.mode === "replay" && envelope\.handoff === "REPLAY_READY"/);
  assert.match(sessionHook, /setViewingMode\("replay"\)/);
  assert.match(sessionHook, /currentSession\?\.replayReady/);
});

