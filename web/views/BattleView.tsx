import { useMemo, useState } from "react";

import { BattleDriverCard } from "../components/battle/BattleDriverCard";
import { Panel } from "../components/shared/Panel";
import { gapBetween, recommendedBattle } from "../domain/battle";
import type { Driver, RaceState } from "../domain/protocol";

type BattleMode = "recommended" | "leader" | "pinned";
type GapSample = { at: string; value: number };

function GapHistory({ samples }: { samples: GapSample[] }) {
  if (samples.length < 2) return <div className="battle-chart-empty">GAP HISTORY BUILDS FROM FACTUAL REPLAY OBSERVATIONS</div>;
  const values = samples.map((sample) => sample.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 0.1);
  const points = samples.map((sample, index) => `${(index / Math.max(samples.length - 1, 1)) * 100},${38 - ((sample.value - min) / range) * 30}`).join(" ");
  return <div className="battle-chart"><svg viewBox="0 0 100 42" preserveAspectRatio="none" aria-label="Observed gap history"><line x1="0" y1="38" x2="100" y2="38" /><polyline points={points} /></svg><span>{min.toFixed(3)}s</span><strong>{max.toFixed(3)}s</strong></div>;
}

export function BattleView({ state, stateHistory }: { state: RaceState; stateHistory: RaceState[] }) {
  const drivers = useMemo(() => Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999)), [state.drivers]);
  const [mode, setMode] = useState<BattleMode>("recommended");
  const [pinned, setPinned] = useState<[string, string]>(["", ""]);
  const recommended = recommendedBattle(drivers);
  const leaderPair = drivers.length >= 2 ? [drivers[0], drivers[1]] as [Driver, Driver] : null;
  const pinnedPair = [drivers.find((driver) => driver.number === pinned[0]) ?? null, drivers.find((driver) => driver.number === pinned[1]) ?? null] as const;
  const pair = mode === "recommended" ? recommended : mode === "leader" ? leaderPair : pinnedPair[0] && pinnedPair[1] ? [pinnedPair[0], pinnedPair[1]] as [Driver, Driver] : null;
  const left = pair?.[0] ?? null;
  const right = pair?.[1] ?? null;
  const gap = gapBetween(left, right);
  const samples: GapSample[] = !left || !right ? [] : stateHistory.flatMap((snapshot) => {
      const value = gapBetween(snapshot.drivers[left.number] ?? null, snapshot.drivers[right.number] ?? null);
      return snapshot.updated_at && value != null ? [{ at: snapshot.updated_at, value }] : [];
    });
  const trend = samples.length < 3 ? "INSUFFICIENT HISTORY" : samples.at(-1)!.value < samples[0].value - 0.05 ? "CLOSING" : samples.at(-1)!.value > samples[0].value + 0.05 ? "OPENING" : "STABLE";

  return <div className="battle-view">
    <header className="experience-heading"><div><span>FACTUAL COMPARISON</span><h1>Battle</h1><p>Two drivers, one shared gap, no invented strategy.</p></div><div className="battle-modes">{(["recommended", "leader", "pinned"] as const).map((item) => <button className={mode === item ? "active" : ""} key={item} onClick={() => setMode(item)}>{item.toUpperCase()}</button>)}</div></header>
    <div className="battle-selectors"><label><span>DRIVER A</span><select value={left?.number ?? pinned[0]} onChange={(event) => { setPinned([event.target.value, pinned[1]]); setMode("pinned"); }}>{drivers.map((driver) => <option key={driver.number} value={driver.number}>P{driver.position ?? "-"} · {driver.code ?? driver.number}</option>)}</select></label><div><span>OBSERVED GAP</span><strong>{gap == null ? "-" : `${gap.toFixed(3)}s`}</strong><small className={`trend trend-${trend.toLowerCase().split(" ")[0]}`}>{trend}</small></div><label><span>DRIVER B</span><select value={right?.number ?? pinned[1]} onChange={(event) => { setPinned([pinned[0], event.target.value]); setMode("pinned"); }}>{drivers.map((driver) => <option key={driver.number} value={driver.number}>P{driver.position ?? "-"} · {driver.code ?? driver.number}</option>)}</select></label></div>
    <div className="battle-symmetric"><BattleDriverCard driver={left} side="left" /><div className="battle-axis"><i /><span>TRACK ORDER</span></div><BattleDriverCard driver={right} side="right" /></div>
    <div className="battle-lower"><Panel eyebrow="OBSERVED" title="Gap history"><GapHistory samples={samples} /></Panel><Panel eyebrow="MINISECTORS" title="Precision status"><div className="unknown-block"><strong>NOT AVAILABLE</strong><p>The current source exposes sectors, not factual minisector state.</p></div></Panel><Panel eyebrow="STRATEGY" title="Interaction"><div className="unknown-block"><strong>ANALYTICS NOT ENABLED</strong><p>No undercut, overcut, or predicted pass value is inferred.</p></div></Panel></div>
  </div>;
}
