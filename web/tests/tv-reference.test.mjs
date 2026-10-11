import assert from "node:assert/strict";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
const server = await createServer({ configLoader: "runner", root: fileURLToPath(new URL("..", import.meta.url)), server: { middlewareMode: true, hmr: false }, appType: "custom" });
after(() => server.close());
const { ObservedLapBars } = await server.ssrLoadModule("/components/analysis/TVFollowing.tsx");
const { TVResult } = await server.ssrLoadModule("/components/analysis/TVResult.tsx");
const { describeStory } = await server.ssrLoadModule("/components/story/presentation.ts");
const { EMPTY_RACE_STATE } = await server.ssrLoadModule("/domain/protocol.ts");
const render = (component, props) => renderToStaticMarkup(createElement(component, props));

test("following lap bars distinguish representative best laps from unknown and pit laps", () => {
  const samples = [
    { lap: 1, stintNumber: 1, rawLapTime: 80, quality: "representative", contaminationReasons: [] },
    { lap: 2, stintNumber: 1, rawLapTime: 79, quality: "unknown", contaminationReasons: [] },
    { lap: 3, stintNumber: 1, rawLapTime: 90, quality: "contaminated", contaminationReasons: ["pit_out"] },
  ];
  const html = render(ObservedLapBars, { samples });
  assert.equal((html.match(/is-best/g) ?? []).length, 1);
  assert.match(html, /1:20.000 \(best clean lap\)/);
  assert.match(html, /is-pit/);
  assert.doesNotMatch(render(ObservedLapBars, { samples: samples.slice(1) }), /is-best|best clean lap/);
});

test("TV results wait for the server verdict and never duplicate a tied podium slot", () => {
  const drivers = Object.fromEntries([1, 2, 3].map(number => [String(number), { number: String(number), code: `D${number}`, name: `Driver ${number}`, position: number === 3 ? 2 : number, activity: "ON_TRACK", source_condition: "RUNNING", classification: null }]));
  const state = { ...EMPTY_RACE_STATE, drivers };
  assert.doesNotMatch(render(TVResult, { state, analytics: { story: { result: { state: "none" }, events: [] } } }), /WINNER ON THE ROAD|ref-result-pod /);
  const html = render(TVResult, { state, analytics: { story: { result: { state: "provisional" }, events: [] } } });
  assert.match(html, /PROVISIONAL/);
  assert.doesNotMatch(html, /ref-result-p2|WINNER ON THE ROAD|FINAL CLASSIFICATION/);
});

test("reference flag and elimination cards keep official status and source segment", () => {
  const event = { kind: "FLAG", data: { flag: "VSC" }, driverNumbers: [], title: "Virtual safety car", detail: "Official whole-track status", phase: "Q3" };
  assert.deepEqual([describeStory(event).tag, describeStory(event).title, describeStory(event).detail], ["VSC", "Virtual Safety Car", "deployed"]);
  assert.equal(describeStory({ ...event, kind: "ELIMINATED", data: { phase: "Q1" } }).tag, "OUT IN Q1");
});
