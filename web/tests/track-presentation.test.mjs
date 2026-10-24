import assert from "node:assert/strict";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { act, createElement, useRef } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<div id='root'></div>", { url: "http://localhost" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
const { createRoot } = await import("react-dom/client");
const server = await createServer({ configLoader:"runner", cacheDir:"../.codex-tmp/vite-tests", root:fileURLToPath(new URL("..", import.meta.url)), server:{ middlewareMode:true, hmr:false }, appType:"custom" });
after(() => server.close());
after(() => dom.window.close());
const { EMPTY_RACE_STATE } = await server.ssrLoadModule("/domain/protocol.ts");
const { buildTrackGeometry } = await server.ssrLoadModule("/domain/trackGeometry.ts");
const { TrackMap } = await server.ssrLoadModule("/components/analysis/TrackMap.tsx");
const { RaceOrderRibbon } = await server.ssrLoadModule("/components/analysis/RaceOrderRibbon.tsx");
const { useTrackMotion, useTrackViewport } = await server.ssrLoadModule("/hooks/useTrackPresentation.ts");
const { packAxis, packMapCars, mapMarkerOffsets, trackNormal, focusWithNeighbours, observedProgressDelta, sourceLeaderGap, sourceLapGap, ribbonScale } = await server.ssrLoadModule("/components/analysis/trackPresentation.ts");
const driver = { number:"1", code:"ONE", name:"Driver One", team:"Team", team_colour:"ff0000", position:1, lap:12, compound:"SOFT", tyre_age:5, stint_laps:5, pit_count:2, gap_to_leader:null, source_condition:"RUNNING", status:"RUNNING", activity:"ON_TRACK", classification:null, availability:{}, track_position:.1, x:null, y:null };
const geometry = buildTrackGeometry([[0,0],[100,0],[100,100],[0,100]],0);
// Invert this square fixture's path to verify motion remains on its edges.
function assertOnPathBetween(point, lower, upper) {
  const points=[...geometry.points,geometry.points[0]];
  for(let i=0;i<4;i++) {
    const a=points[i],b=points[i+1],dx=b.x-a.x,dy=b.y-a.y;
    const t=((point[0]-a.x)*dx+(point[1]-a.y)*dy)/(dx*dx+dy*dy);
    if(t>=0 && t<=1 && Math.hypot(point[0]-a.x-t*dx,point[1]-a.y-t*dy)<.02) {
      const fraction=(i+t)/4;
      assert.ok(fraction>lower && fraction<upper,`${fraction} is between ${lower} and ${upper}`);
      return;
    }
  }
  assert.fail(`point ${point} left the track path`);
}
const mapProps = { circuit:{ ...EMPTY_RACE_STATE.circuit, path:[[0,0],[100,0],[100,100],[0,100]] }, session:{ ...EMPTY_RACE_STATE.session, session_kind:"race" }, positionMode:"timing_estimate", viewingMode:"replay" };
const render = (Component, props) => new JSDOM(renderToStaticMarkup(createElement(Component,props))).window.document;

test("all 22 coincident timing points have distinct visible symbols without changing progress", () => {
  const drivers = Array.from({length:22}, (_,index) => ({...driver,number:String(index+1),position:index+1}));
  const cars = drivers.map((driver,priority)=>({driver,priority,focus:false,fraction:.1,point:{x:975,y:620},normal:{x:0,y:1}}));
  const offsets = mapMarkerOffsets(packMapCars(cars,12,14,6),12);
  const points = cars.map(car=>({x:car.point.x+offsets.get(car.driver.number).x,y:car.point.y+offsets.get(car.driver.number).y}));
  for (let i=0;i<points.length;i++) {
    assert.ok(points[i].x>=12 && points[i].x<=988 && points[i].y>=12 && points[i].y<=638);
    for(let j=i+1;j<points.length;j++) assert.ok(Math.hypot(points[i].x-points[j].x,points[i].y-points[j].y)>=28.79);
  }
  assert.ok(cars.every(car=>car.fraction===.1 && car.point.x===975 && car.point.y===620));
  const page=render(TrackMap,{...mapProps,drivers});
  const dots=[...page.querySelectorAll('.track-car-dot')];
  assert.equal(dots.length,22);
  assert.ok(dots.every(dot=>dot.getAttribute('cx')==='0' && dot.getAttribute('cy')==='0'),"car dots stay at their path anchors");
  const badges=[...page.querySelectorAll('.track-car-badge')];
  assert.equal(badges.length,21,"every displaced car retains an individually visible label");
  assert.equal(new Set(badges.map(badge=>badge.getAttribute('transform'))).size,21);
  assert.match(page.querySelector('.track-group-note').textContent,/separated/);
  // Neighbouring groups must share collision checks, or expanding one cluster
  // can hide the cars in the next mini-sector again.
  const neighbours=cars.map((car,index)=>({...car,point:{x:index<11?940:975,y:620}}));
  const nearbyOffsets=mapMarkerOffsets(packMapCars(neighbours,12,14,6),12);
  const nearby=neighbours.map(car=>({x:car.point.x+nearbyOffsets.get(car.driver.number).x,y:car.point.y+nearbyOffsets.get(car.driver.number).y}));
  for(let i=0;i<nearby.length;i++) for(let j=i+1;j<nearby.length;j++) assert.ok(Math.hypot(nearby[i].x-nearby[j].x,nearby[i].y-nearby[j].y)>=28.79);
});

test("leader, followed driver and neighbours keep the same dot size as positions change", () => {
  const drivers=Array.from({length:5},(_,index)=>({...driver,number:String(index+1),position:index+1,track_position:.1+index*.15}));
  const sizes=rows=>new Map([...render(TrackMap,{...mapProps,drivers:rows,focusedDriverNumbers:["3"]}).querySelectorAll("[data-track-driver]")].map(node=>[node.getAttribute("data-track-driver"),node.querySelector(".track-car-dot").getAttribute("r")]));
  const before=sizes(drivers),after=sizes(drivers.map((item,index)=>({...item,position:5-index})));
  assert.equal(new Set(before.values()).size,1);
  assert.deepEqual(after,before);
});

test("timing axis accepts only finite source gaps and explicit lap deficits", () => {
  for (const raw of [null,"","—","-1.5","1:05","+1 LAP","NaN","Infinity","1e2","9".repeat(400)]) assert.equal(sourceLeaderGap({ ...driver, position:2, gap_to_leader:raw }),null,raw);
  assert.equal(sourceLeaderGap({ ...driver,position:2,gap_to_leader:"+1.234" }),1.234);
  assert.equal(sourceLeaderGap({ ...driver,position:2,gap_to_leader:"+1.234",availability:{gap_to_leader:"unavailable"} }),null);
  assert.equal(sourceLeaderGap(driver),0);
  assert.equal(sourceLapGap({ ...driver,gap_to_leader:"+2 LAPS" }),true);
  assert.equal(sourceLapGap({ ...driver,gap_to_leader:"+2 LAPS",availability:{gap_to_leader:"unavailable"} }),false);
  assert.ok(ribbonScale(245)>245,"large source gaps remain on the time axis");
});

test("pixel packing clusters coincident cars and prioritizes focused labels", () => {
  const placements=packAxis([{key:"a",x:40,priority:0,focus:false,label:"ONE"},{key:"b",x:42,priority:1,focus:true,label:"TWO"},{key:"c",x:120,priority:2,focus:false,label:"THR"}],"phone",180);
  assert.equal(placements.get("a").show,false);
  assert.equal(placements.get("b").show,true);
  assert.equal(placements.get("b").count,2);
  assert.equal(placements.get("b").lane,0);
  const tvItems=[{key:"one",x:80,priority:0,focus:false,label:"ONE"},{key:"two",x:100,priority:1,focus:false,label:"TWO"}];
  assert.equal([...packAxis(tvItems,"tv",300,1).values()].filter(item=>item.show).length,2);
  assert.equal([...packAxis(tvItems,"tv",300,2).values()].filter(item=>item.show).length,1,"4K packing uses the same doubled dot/font size as TV CSS");
  assert.equal([...packAxis(tvItems,"tv",300,.7).values()].filter(item=>item.show).length,2);
  const cars=[.1,.101,.6].map((fraction,index)=>({driver:{...driver,number:String(index+1),code:["ONE","TWO","THR"][index]},point:geometry.pointAt(fraction),fraction,normal:trackNormal(geometry,fraction),priority:index,focus:index===1}));
  const groups=packMapCars(cars,12,18,3);
  const clustered=groups.find(group=>group.members.length===2);
  assert.equal(groups.length,2);
  assert.equal(clustered.representative.driver.code,"TWO");
  assert.deepEqual(clustered.point, clustered.representative.point, "a selected cluster representative ends at its own progress, not another car's point");
  assert.ok(clustered.label && Math.hypot(clustered.label.x,clustered.label.y)>12);
  assert.deepEqual([...focusWithNeighbours([1,2,3,4].map(position=>({...driver,number:String(position),position})),["3"])].sort(),["2","3","4"]);
});

test("map keeps every active dot while packing labels, with source pit and stopped trays", () => {
  const page=render(TrackMap,{...mapProps,drivers:[driver,{...driver,number:"2",code:"TWO",position:2,track_position:.1001},{...driver,number:"3",code:"PIT",position:3,source_condition:"IN_PIT",activity:"IN_PIT"},{...driver,number:"4",code:"OUT",position:4,source_condition:"STOPPED"}]});
  assert.equal(page.querySelectorAll(".car-marker").length,2);
  assert.equal(page.querySelectorAll('[data-track-driver][visibility="hidden"]').length,0);
  assert.equal(page.querySelectorAll(".track-car-label").length,1);
  const label=page.querySelector(".track-car-label");
  assert.ok(Number(label.getAttribute("x"))!==0 || Number(label.getAttribute("y"))!==0);
  assert.equal(page.querySelector(".map-pit-list em").textContent,"PIT");
  assert.match(page.querySelector(".map-out-list").textContent,/OUT/);
  assert.doesNotMatch(page.querySelector(".map-out-list").textContent,/PIT/);
  assert.equal(page.querySelector(".map-center"),null);
  assert.ok(page.querySelector(".race-order-ribbon"));
  assert.equal(render(TrackMap,{...mapProps,drivers:[driver],focusedDriverNumbers:["1"]}).querySelector(".race-order-ribbon"),null);
});

test("unavailable positions do not use cached fractions; known progress survives a missing outline", () => {
  const unavailable=render(TrackMap,{...mapProps,drivers:[driver],positionMode:"unavailable"});
  assert.equal(unavailable.querySelectorAll(".car-marker").length,0);
  assert.match(unavailable.body.textContent,/CAR POSITION NOT AVAILABLE FOR THIS REPLAY/);
  const line=render(TrackMap,{...mapProps,circuit:EMPTY_RACE_STATE.circuit,drivers:[driver]});
  assert.ok(line.querySelector(".track-line"));
  assert.equal(line.querySelectorAll(".track-axis-dot").length,2,"one progress dot and one independent timing-axis dot");
  assert.match(line.body.textContent,/SHAPE · UNAVAILABLE/);
});

test("ribbon separates lap deficits and draws battle links only for server-comparable pairs", () => {
  const drivers=[driver,{...driver,number:"2",code:"TWO",position:2,gap_to_leader:"+1.234"},{...driver,number:"3",code:"LAP",position:3,gap_to_leader:"+1 LAP"},{...driver,number:"4",code:"UNK",position:4,gap_to_leader:null}];
  const page=render(RaceOrderRibbon,{drivers,battlePairs:[{aheadDriverNumber:"1",behindDriverNumber:"2",comparisonState:"COMPARABLE"},{aheadDriverNumber:"2",behindDriverNumber:"4",comparisonState:"UNAVAILABLE"}]});
  assert.equal(page.querySelectorAll(".rb-links i").length,1);
  assert.equal(page.querySelector(".rb-lapped em").textContent,"LAP");
  assert.equal(page.querySelectorAll(".rb-cars [data-axis-driver]").length,2);
  assert.equal(page.querySelector('.rb-cars [data-axis-driver="3"]'),null);
  assert.equal(page.querySelector('.rb-cars [data-axis-driver="4"]'),null);
});

test("progress interpolation rejects backward corrections and accepts only bounded forward travel", () => {
  assert.equal(observedProgressDelta(.1,.2,3,3),.1);
  assert.ok(Math.abs(observedProgressDelta(.98,.02,3,4)-.04)<1e-10);
  assert.ok(Math.abs(observedProgressDelta(22/24,4/24,3,4)-.25)<1e-10);
  for(const args of [[.5,.4,3,3],[.1,.8,3,3],[.5,.6,4,3],[NaN,.2,3,3]]) assert.equal(observedProgressDelta(...args),null);
});

test("map motion stays between received endpoints and snaps on navigation, reduced motion and high speed", async () => {
  let now=1000, nextId=0;
  const frames=new Map();
  window.requestAnimationFrame=callback=>{ const id=++nextId; frames.set(id,callback); return id; };
  window.cancelAnimationFrame=id=>frames.delete(id);
  Object.defineProperty(window.performance,"now",{configurable:true,value:()=>now});
  const flush=delta=>{now+=delta;const callbacks=[...frames.values()];frames.clear();callbacks.forEach(callback=>callback(now));};
  // Test-only fixture harness; the production hook owns its TypeScript input contract.
  // eslint-disable-next-line react/prop-types
  function Harness({fraction,generation=1,reduced=false,speed=1,asOf,playing=true,hasGeometry=true}) {
    const ref=useRef(null),point=geometry.pointAt(fraction);
    useTrackMotion(ref,[{number:"1",point,fraction,lap:12}],hasGeometry ? geometry : null,{navigationGeneration:generation,playing,reducedMotion:reduced,speed,asOf});
    return createElement("svg",{ref},createElement("g",{"data-track-driver":"1",transform:`translate(${point.x} ${point.y})`}));
  }
  const container=document.getElementById("root"),root=createRoot(container);
  const update=async props=>{await act(async()=>root.render(createElement(Harness,props)));};
  const current=()=>container.querySelector("g").getAttribute("transform").match(/[-+]?\d*\.?\d+/g).map(Number);
  const at=fraction=>Object.values(geometry.pointAt(fraction)).map(value=>Math.round(value*100)/100);
  try {
    await update({fraction:.1,asOf:"2026-01-01T00:00:01Z"});
    assert.deepEqual(current(),at(.1));assert.equal(frames.size,0);
    await update({fraction:.2,asOf:"2026-01-01T00:00:02Z"});
    assert.deepEqual(current(),at(.1));
    flush(500);assertOnPathBetween(current(), .1, .2);
    const middle=current();
    flush(500);assertOnPathBetween(current(), .1, .2);assert.notDeepEqual(current(),middle);
    assert.equal(frames.size,1,"approach eases instead of stopping at a fixed packet deadline");
    flush(5000);assert.deepEqual(current(),at(.2));assert.equal(frames.size,0);
    flush(10000);assert.deepEqual(current(),at(.2),"no future position extrapolation");
    await update({fraction:.3,generation:2,asOf:"2026-01-01T00:00:03Z"});
    assert.deepEqual(current(),at(.3));assert.equal(frames.size,0);
    await update({fraction:.4,generation:2,reduced:true,asOf:"2026-01-01T00:00:04Z"});
    assert.deepEqual(current(),at(.4));assert.equal(frames.size,0);
    await update({fraction:.5,generation:2,speed:30,asOf:"2026-01-01T00:00:05Z"});
    assert.deepEqual(current(),at(.5));assert.equal(frames.size,0);
    await update({fraction:.45,generation:2,asOf:"2026-01-01T00:00:06Z"});
    assert.deepEqual(current(),at(.45));assert.equal(frames.size,0);
    await update({fraction:.5,generation:2,asOf:"2026-01-01T00:00:07Z"});
    flush(200);
    await update({fraction:.5,generation:2,asOf:"2026-01-01T00:00:07Z",playing:false});
    assert.deepEqual(current(),at(.5));assert.equal(frames.size,0);
    await update({fraction:.6,generation:2,asOf:"2026-01-01T00:00:08Z"});
    assert.equal(frames.size,1);
    await update({fraction:.6,generation:2,hasGeometry:false,asOf:"2026-01-01T00:00:08Z"});
    assert.equal(frames.size,0,"missing geometry cancels the pending animation");
    await update({fraction:.6,generation:2,asOf:"2026-01-01T00:00:08Z"});
    assert.deepEqual(current(),at(.6));assert.equal(frames.size,0);
    await update({fraction:.7,generation:2,asOf:"2026-01-01T00:00:09Z"});
    assert.equal(frames.size,1,"motion resumes after geometry returns");
    await act(async()=>root.unmount());
    assert.equal(frames.size,0,"unmount cancels its animation");
  } finally { await act(async()=>root.unmount()); delete window.requestAnimationFrame;delete window.cancelAnimationFrame; }
});

test("sparse per-car updates travel around corners at their own cadence despite intervening packets", async () => {
  let now = 1000, id = 0;
  const frames = new Map();
  window.requestAnimationFrame = callback => { frames.set(++id, callback); return id; };
  window.cancelAnimationFrame = key => frames.delete(key);
  Object.defineProperty(window.performance, "now", { configurable: true, value: () => now });
  const flush = delta => { now += delta; const callbacks = [...frames.values()]; frames.clear(); callbacks.forEach(callback => callback(now)); };
  // eslint-disable-next-line react/prop-types
  function Harness({ fraction, asOf }) {
    const ref = useRef(null), point = geometry.pointAt(fraction);
    useTrackMotion(ref, [{ number: "1", point, fraction, lap: 12 }], geometry, { playing: true, speed: 1, asOf });
    return createElement("svg", { ref }, createElement("g", { "data-track-driver": "1", transform: `translate(${point.x} ${point.y})` }));
  }
  const root = createRoot(document.getElementById("root"));
  const update = async (fraction, seconds) => { await act(async () => root.render(createElement(Harness, { fraction, asOf: seconds == null ? undefined : `2026-01-01T00:00:${String(seconds).padStart(2, "0")}Z` }))); };
  const at = fraction => Object.values(geometry.pointAt(fraction)).map(value => Math.round(value * 100) / 100);
  const current = () => document.querySelector("[data-track-driver]").getAttribute("transform").match(/[-+]?\d*\.?\d+/g).map(Number);
  try {
    await update(.2, 1);
    flush(7000); await update(.2, 8); // Another driver's packet; this driver has not moved.
    flush(1000); await update(.4, 9);
    flush(4000); assertOnPathBetween(current(), .25, .4);
    const middle=current(), pending=[...frames.keys()];
    await update(.4, 13); assert.deepEqual(current(), middle, "same endpoint does not restart or overwrite animation");
    assert.deepEqual([...frames.keys()],pending,"unrelated packets preserve the pending animation tick");
    flush(4000); assertOnPathBetween(current(), .25, .4);
    flush(20000); assert.deepEqual(current(), at(.4), "never extrapolate beyond a received endpoint");
    // Desktop maps without an explicit source clock use per-driver receipt times.
    await update(.5, null); flush(60000); assert.deepEqual(current(), at(.5));
    await update(.6, null); flush(7500); assertOnPathBetween(current(), .5, .6);
  } finally { await act(async () => root.unmount()); delete window.requestAnimationFrame; delete window.cancelAnimationFrame; }
});

for (const posture of ["desktop", "tv"]) test(`${posture}: nearby cars keep visible nodes when merging, changing focus and separating`, async () => {
  let now = 1000, id = 0;
  const frames = new Map();
  window.requestAnimationFrame = callback => { frames.set(++id, callback); return id; };
  window.cancelAnimationFrame = key => frames.delete(key);
  Object.defineProperty(window.performance, "now", { configurable: true, value: () => now });
  const root = createRoot(document.getElementById("root"));
  const update = async (fraction, focus = []) => { await act(async () => root.render(createElement(TrackMap, { ...mapProps, posture, circuit: structuredClone(mapProps.circuit), drivers: [driver, { ...driver, number: "2", code: "TWO", position: 2, track_position: fraction }], focusedDriverNumbers: focus, playing: true, asOf: new Date(Date.UTC(2026, 0, 1) + now).toISOString() }))); };
  try {
    await update(.1001);
    const node = document.querySelector('[data-track-driver="2"]');
    assert.equal(node.getAttribute("visibility"), null);
    now += 1000; await update(.2);
    assert.equal(document.querySelector('[data-track-driver="2"]'), node);
    assert.equal(node.getAttribute("visibility"), null);
    assert.equal(node.dataset.trackMoving, "true");
    now += 500; const callbacks = [...frames.values()]; frames.clear(); callbacks.forEach(callback => callback(now));
    const midpoint = node.getAttribute("transform");
    await update(.2, ["2"]);
    assert.equal(node.getAttribute("transform"), midpoint);
    assert.equal(node.dataset.trackMoving, "true", "fresh but equal path arrays and focus changes preserve motion");
  } finally { await act(async () => root.unmount()); delete window.requestAnimationFrame; delete window.cancelAnimationFrame; }
});

for (const explicitClock of [false, true]) test(`map burst and lap-wrap motion remains continuous with ${explicitClock ? "TV" : "shared shell"} clock`, async () => {
  let now = 1000, id = 0;
  const frames = new Map();
  window.requestAnimationFrame = callback => { frames.set(++id, callback); return id; };
  window.cancelAnimationFrame = key => frames.delete(key);
  Object.defineProperty(window.performance, "now", { configurable: true, value: () => now });
  const flush = delta => { now += delta; const callbacks = [...frames.values()]; frames.clear(); callbacks.forEach(callback => callback(now)); };
  // eslint-disable-next-line react/prop-types
  function Harness({ fraction, lap, at, generation }) {
    const ref = useRef(null), point = geometry.pointAt(fraction);
    useTrackMotion(ref, [{ number: "1", point, fraction, lap }], geometry,
      { playing: true, speed: 1, navigationGeneration: generation, ...(explicitClock ? { asOf: at } : {}) });
    return createElement("div", { className: "app-shell", "data-viewer-time": at },
      createElement("svg", { ref }, createElement("g", { "data-track-driver": "1", transform: `translate(${point.x} ${point.y})` })));
  }
  const root = createRoot(document.getElementById("root"));
  const update = async (fraction, sourceMs, lap = 12, generation = 1) => {
    const at = new Date(Date.UTC(2026, 0, 1) + sourceMs).toISOString();
    await act(async () => root.render(createElement(Harness, { fraction, lap, at, generation })));
  };
  const at = fraction => Object.values(geometry.pointAt(fraction)).map(value => Math.round(value * 100) / 100);
  const current = () => document.querySelector("[data-track-driver]").getAttribute("transform").match(/[-+]?\d*\.?\d+/g).map(Number);
  const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  try {
    await update(.1, 1000);
    flush(1000); await update(.2, 2000);
    flush(100); assertOnPathBetween(current(), .1, .2);
    const burstStart=current();
    // Two close source packets must not accelerate the unfinished .1 lap
    // of display travel into the 20 ms between them.
    await update(.21, 2020);
    assert.deepEqual(current(), burstStart);
    flush(100);
    assert.ok(distance(current(), burstStart) > 0);
    assert.ok(distance(current(), burstStart) < distance(at(.13), at(.11)));

    await update(.85, 3000, 12, 2);
    flush(1000); await update(.95, 4000, 12, 2);
    flush(400); assertOnPathBetween(current(), .85, .95);
    const wrapStart=current();
    await update(.02, 4400, 13, 2);
    assert.deepEqual(current(), wrapStart, "start/finish wrap never snaps a lagging dot");
    flush(100);
    const before = current();
    await update(.12, 5000, 13, 2);
    await update(.22, 6000, 13, 2);
    assert.deepEqual(current(), before, "a display backlog over quarter-lap is not a source discontinuity");
    flush(15000); assert.deepEqual(current(), at(.22));
    flush(30000); assert.deepEqual(current(), at(.22), "no prediction beyond the last received position");
  } finally { await act(async () => root.unmount()); delete window.requestAnimationFrame; delete window.cancelAnimationFrame; }
});


test("a new endpoint preserves displayed velocity and eases to a bounded stop", async () => {
  let now=1000,id=0;
  const frames=new Map();
  window.requestAnimationFrame=callback=>{frames.set(++id,callback);return id;};
  window.cancelAnimationFrame=key=>frames.delete(key);
  Object.defineProperty(window.performance,"now",{configurable:true,value:()=>now});
  const flush=ms=>{now+=ms;const callbacks=[...frames.values()];frames.clear();callbacks.forEach(callback=>callback(now));};
  // eslint-disable-next-line react/prop-types
  function Harness({fraction,asOf}) {
    const ref=useRef(null),point=geometry.pointAt(fraction);
    useTrackMotion(ref,[{number:"1",point,fraction,lap:1}],geometry,{playing:true,speed:1,asOf});
    return createElement("svg",{ref},createElement("g",{"data-track-driver":"1"}));
  }
  const root=createRoot(document.getElementById("root"));
  const update=async(fraction,ms)=>{await act(async()=>root.render(createElement(Harness,{fraction,asOf:new Date(Date.UTC(2026,0,1)+ms).toISOString()})));};
  const x=()=>Number(document.querySelector("[data-track-driver]").getAttribute("transform").match(/[-+]?\d*\.?\d+/)[0]);
  try {
    await update(.1,1000);flush(1000);await update(.2,2000);
    flush(240);const before=x();flush(10);const junction=x(),incoming=junction-before;
    await update(.21,2250);assert.equal(x(),junction,"retarget must not jump");
    flush(10);const outgoing=x()-junction;
    assert.ok(outgoing/incoming>.8 && outgoing/incoming<1.2,"retarget must not abruptly change speed");
    let previous=x();
    for(let i=0;i<500;i++) {
      flush(16);const current=x();
      assert.ok(current>=previous,"never reverse");
      assert.ok(current<=geometry.pointAt(.21).x+.01,"never predict beyond the latest endpoint");
      previous=current;
    }
    assert.equal(frames.size,0,"settles without a permanent animation loop");
  } finally {await act(async()=>root.unmount());delete window.requestAnimationFrame;delete window.cancelAnimationFrame;}
});

test("track viewport reads authored TV scale for pixel marker and label sizes", async () => {
  const oldObserver=globalThis.ResizeObserver, oldBounds=window.HTMLElement.prototype.getBoundingClientRect;
  let resize;
  globalThis.ResizeObserver=class { constructor(callback) {resize=callback;} observe() {resize();} disconnect() {} };
  window.HTMLElement.prototype.getBoundingClientRect=()=>({width:1200,height:600,top:0,left:0,right:1200,bottom:600});
  // Test-only fixture harness; the production hook owns its TypeScript input contract.
  // eslint-disable-next-line react/prop-types
  function Harness({scale}) {
    const ref=useRef(null),viewport=useTrackViewport(ref,"tv");
    return createElement("div",{ref,style:{"--tv-scale":scale},"data-size":`${viewport.width}:${viewport.height}:${viewport.scale}`});
  }
  const root=createRoot(document.getElementById("root"));
  try {
    await act(async()=>root.render(createElement(Harness,{scale:2})));
    assert.equal(document.querySelector("[data-size]").dataset.size,"1200:600:2");
    await act(async()=>root.render(createElement(Harness,{scale:.711})));
    await act(async()=>resize());
    assert.equal(document.querySelector("[data-size]").dataset.size,"1200:600:0.711");
  } finally {
    await act(async()=>root.unmount());globalThis.ResizeObserver=oldObserver;window.HTMLElement.prototype.getBoundingClientRect=oldBounds;
  }
});
