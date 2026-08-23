import { useMemo, useState } from "react";

import { BattlePublishedContext } from "../components/analysis/PublishedStrategy";
import { TrackMap } from "../components/analysis/TrackMap";
import { BattleDriverCard } from "../components/battle/BattleDriverCard";
import { Panel } from "../components/shared/Panel";
import { currentPairGap } from "../domain/battle";
import { driverLifecycle } from "../domain/lifecycle";
import type { AnalyticsSnapshot, Driver, PositionMode, RaceState } from "../domain/protocol";

type BattleMode = "recommended" | "leader" | "pinned";
type GapSample = { occurredAt: string; lap: number; gapSeconds: number };

function GapHistory({ samples }: { samples: GapSample[] }) {
  if (samples.length < 2) return <div className="battle-chart-empty">COMPLETED-LAP GAP HISTORY IS NOT YET AVAILABLE FOR THIS PAIR</div>;
  const values = samples.map((sample) => sample.gapSeconds);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 0.1);
  const points = samples.map((sample, index) => `${(index / Math.max(samples.length - 1, 1)) * 100},${34 - ((sample.gapSeconds - min) / range) * 27}`).join(" ");
  return <div className="battle-chart"><div className="battle-chart-axis"><span>GAP (S)</span><small>{max.toFixed(2)}</small><small>{min.toFixed(2)}</small></div><svg viewBox="0 0 100 38" preserveAspectRatio="none" aria-label="Completed-lap interval history"><line x1="0" y1="34" x2="100" y2="34" /><polyline points={points} /></svg><footer><span>L{samples[0].lap}</span><strong>COMPLETED LAPS</strong><span>L{samples.at(-1)!.lap}</span></footer></div>;
}

export function BattleView({ state, analytics, recommendedPair, positionMode }: { state: RaceState; analytics: AnalyticsSnapshot | null; recommendedPair: [string, string] | null; positionMode: PositionMode }) {
  const drivers = useMemo(() => Object.values(state.drivers).filter((driver) => driverLifecycle(driver).battleEligible).sort((a, b) => (a.position ?? 999) - (b.position ?? 999)), [state.drivers]);
  const [mode, setMode] = useState<BattleMode>("recommended");
  const [pinned, setPinned] = useState<[string, string]>(["", ""]);
  const recommended = recommendedPair ? [drivers.find((driver) => driver.number === recommendedPair[0]), drivers.find((driver) => driver.number === recommendedPair[1])] as const : null;
  const leaderPair = drivers.length >= 2 ? [drivers[0], drivers[1]] as [Driver, Driver] : null;
  const pinnedPair = [drivers.find((driver) => driver.number === pinned[0]) ?? null, drivers.find((driver) => driver.number === pinned[1]) ?? null] as const;
  const pair = mode === "recommended" ? recommended?.[0] && recommended[1] ? [recommended[0], recommended[1]] as [Driver, Driver] : null : mode === "leader" ? leaderPair : pinnedPair[0] && pinnedPair[1] ? [pinnedPair[0], pinnedPair[1]] as [Driver, Driver] : null;
  const left = pair?.[0] ?? null;
  const right = pair?.[1] ?? null;
  const gap = currentPairGap(analytics, left, right);
  const historyKey = left && right ? `${left.number}:${right.number}` : "";
  const reverseKey = left && right ? `${right.number}:${left.number}` : "";
  const samples = analytics?.battle.histories?.[historyKey] ?? analytics?.battle.histories?.[reverseKey] ?? [];
  const trend = samples.length < 3 ? "INSUFFICIENT HISTORY" : samples.at(-1)!.gapSeconds < samples[0].gapSeconds - 0.05 ? "CLOSING" : samples.at(-1)!.gapSeconds > samples[0].gapSeconds + 0.05 ? "OPENING" : "STABLE";
  const battleCandidate = analytics?.battle.candidates.find((item) => (item.aheadDriverNumber === left?.number && item.behindDriverNumber === right?.number) || (item.aheadDriverNumber === right?.number && item.behindDriverNumber === left?.number)) ?? null;

  return <div className="battle-view">
    <header className="experience-heading"><div><span>RACE INTELLIGENCE</span><h1>Battle</h1><p>Recommended uses completed-lap source history; Leader and Pinned never change its server truth.</p></div><div className="battle-modes">{(["recommended", "leader", "pinned"] as const).map((item) => <button className={mode === item ? "active" : ""} key={item} onClick={() => setMode(item)}>{item.toUpperCase()}</button>)}</div></header>
    <div className="battle-selectors"><label><span>DRIVER A</span><select value={left?.number ?? pinned[0]} onChange={(event) => { setPinned([event.target.value, pinned[1]]); setMode("pinned"); }}><option value="">SELECT</option>{drivers.map((driver) => <option key={driver.number} value={driver.number}>P{driver.position ?? "—"} · {driver.code ?? driver.number}</option>)}</select></label><div><span>OBSERVED INTERVAL</span><strong>{gap == null ? "—" : `${gap.toFixed(3)}s`}</strong><small className={`trend trend-${trend.toLowerCase().split(" ")[0]}`}>{trend}</small></div><label><span>DRIVER B</span><select value={right?.number ?? pinned[1]} onChange={(event) => { setPinned([pinned[0], event.target.value]); setMode("pinned"); }}><option value="">SELECT</option>{drivers.map((driver) => <option key={driver.number} value={driver.number}>P{driver.position ?? "—"} · {driver.code ?? driver.number}</option>)}</select></label></div>
    {mode === "recommended" && !pair && <div className="service-unavailable battle-unavailable"><strong>NO STABILIZED MEANINGFUL BATTLE</strong><p>A recommendation appears only after an eligible pair remains within 12 seconds across completed-lap source history.</p></div>}
      {pair && <div className="battle-focus-grid"><BattleDriverCard driver={left} side="left" published={left ? analytics?.publishedStrategy?.drivers[left.number] : undefined} /><div className="battle-focused-map"><TrackMap circuit={state.circuit} session={state.session} drivers={Object.values(state.drivers)} positionMode={positionMode} focusedDriverNumbers={[left!.number, right!.number]} focusLabel={`${left!.code ?? left!.number} · ${right!.code ?? right!.number}`} /></div><BattleDriverCard driver={right} side="right" published={right ? analytics?.publishedStrategy?.drivers[right.number] : undefined} /></div>}
    <div className="battle-lower">
      <Panel eyebrow="COMPLETED LAPS" title="Gap history"><GapHistory samples={samples} /></Panel>
      <Panel eyebrow="BATTLE SCORE" title={battleCandidate ? `${battleCandidate.score.toFixed(1)} / 100` : "NOT AVAILABLE"}><div className="battle-score-factors">{battleCandidate?.factors.map((factor) => <div key={factor.name}><span>{factor.name.replaceAll("_", " ").toUpperCase()}</span><strong>{factor.weight >= 0 ? "+" : ""}{factor.weight.toFixed(1)}</strong></div>) ?? <div className="panel-empty">PAIR IS NOT A CURRENT MEANINGFUL BATTLE CANDIDATE</div>}</div></Panel>
      <Panel eyebrow="PIRELLI BASELINE" title="Published strategy context"><BattlePublishedContext analytics={analytics} driverNumbers={left && right ? [left.number, right.number] : null} /></Panel>
    </div>
  </div>;
}

