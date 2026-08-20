import { useMemo, useState } from "react";

import { TrackMap } from "../components/analysis/TrackMap";
import { BattleDriverCard } from "../components/battle/BattleDriverCard";
import { Panel } from "../components/shared/Panel";
import { gapBetween } from "../domain/battle";
import type { AnalyticsSnapshot, Driver, RaceState } from "../domain/protocol";

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

export function BattleView({ state, stateHistory, analytics, recommendedPair }: { state: RaceState; stateHistory: RaceState[]; analytics: AnalyticsSnapshot | null; recommendedPair: [string, string] | null }) {
  const drivers = useMemo(() => Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999)), [state.drivers]);
  const [mode, setMode] = useState<BattleMode>("recommended");
  const [pinned, setPinned] = useState<[string, string]>(["", ""]);
  const recommended = recommendedPair ? [drivers.find((driver) => driver.number === recommendedPair[0]), drivers.find((driver) => driver.number === recommendedPair[1])] as const : null;
  const leaderPair = drivers.length >= 2 ? [drivers[0], drivers[1]] as [Driver, Driver] : null;
  const pinnedPair = [drivers.find((driver) => driver.number === pinned[0]) ?? null, drivers.find((driver) => driver.number === pinned[1]) ?? null] as const;
  const pair = mode === "recommended" ? recommended?.[0] && recommended[1] ? [recommended[0], recommended[1]] as [Driver, Driver] : null : mode === "leader" ? leaderPair : pinnedPair[0] && pinnedPair[1] ? [pinnedPair[0], pinnedPair[1]] as [Driver, Driver] : null;
  const left = pair?.[0] ?? null;
  const right = pair?.[1] ?? null;
  const gap = gapBetween(left, right);
  const isRecommended = mode === "recommended";
  const samples: GapSample[] = isRecommended && analytics?.battle.gapHistory ? analytics.battle.gapHistory : (!left || !right ? [] : stateHistory.flatMap((snapshot) => {
      const value = gapBetween(snapshot.drivers[left.number] ?? null, snapshot.drivers[right.number] ?? null);
      return snapshot.updated_at && value != null ? [{ at: snapshot.updated_at, value }] : [];
    }));
  const trend = isRecommended && analytics?.battle.gapTrend ? analytics.battle.gapTrend : (samples.length < 3 ? "INSUFFICIENT HISTORY" : samples.at(-1)!.value < samples[0].value - 0.05 ? "CLOSING" : samples.at(-1)!.value > samples[0].value + 0.05 ? "OPENING" : "STABLE");
  const battleCandidate = analytics?.battle.candidates.find((item) => item.aheadDriverNumber === left?.number && item.behindDriverNumber === right?.number) ?? null;
  const leftStrategy = left ? analytics?.drivers[left.number]?.strategy : null;
  const rightStrategy = right ? analytics?.drivers[right.number]?.strategy : null;
  const leftPace = left ? analytics?.drivers[left.number]?.pace : null;
  const rightPace = right ? analytics?.drivers[right.number]?.pace : null;
  const battleValid = Boolean(
    left?.position != null
    && right?.position != null
    && left.status === "RUNNING" && right.status === "RUNNING"
    && Math.abs((right.lap ?? 0) - (left.lap ?? 0)) <= 1
  );

  return <div className="battle-view">
    <header className="experience-heading"><div><span>RACE INTELLIGENCE</span><h1>Battle</h1><p>One deterministic recommendation shared by desktop and TV.</p></div><div className="battle-modes">{(["recommended", "leader", "pinned"] as const).map((item) => <button className={mode === item ? "active" : ""} key={item} onClick={() => setMode(item)}>{item.toUpperCase()}</button>)}</div></header>
    <div className="battle-selectors"><label><span>DRIVER A</span><select value={left?.number ?? pinned[0]} onChange={(event) => { setPinned([event.target.value, pinned[1]]); setMode("pinned"); }}>{drivers.map((driver) => <option key={driver.number} value={driver.number}>P{driver.position ?? "-"} · {driver.code ?? driver.number}</option>)}</select></label><div><span>OBSERVED GAP</span><strong>{gap == null ? "-" : `${gap.toFixed(3)}s`}</strong><small className={`trend trend-${trend.toLowerCase().split(" ")[0]}`}>{trend}</small></div><label><span>DRIVER B</span><select value={right?.number ?? pinned[1]} onChange={(event) => { setPinned([pinned[0], event.target.value]); setMode("pinned"); }}>{drivers.map((driver) => <option key={driver.number} value={driver.number}>P{driver.position ?? "-"} · {driver.code ?? driver.number}</option>)}</select></label></div>
    <div className="battle-symmetric"><BattleDriverCard driver={left} side="left" /><div className="battle-axis"><TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={state.circuit.path ? "precise_xy" : "unavailable"} focusDrivers={[left?.number ?? "", right?.number ?? ""]} /></div><BattleDriverCard driver={right} side="right" /></div>
    <div className="battle-lower">
      <Panel eyebrow="OBSERVED" title="Gap history"><GapHistory samples={samples} /></Panel>
      {battleValid ? (
        <Panel eyebrow="BATTLE SCORE" title={battleCandidate ? `${battleCandidate.score.toFixed(1)} / 100` : "—"}>
          <div className="battle-score-factors">{battleCandidate?.factors.map((factor) => <div key={factor.name}><span>{factor.name.replaceAll("_", " ").toUpperCase()}</span><strong>{factor.weight >= 0 ? "+" : ""}{factor.weight.toFixed(1)}</strong></div>) ?? <div className="panel-empty">INSUFFICIENT COMPARABLE EVIDENCE</div>}</div>
        </Panel>
      ) : (
        <Panel eyebrow="BATTLE SCORE" title="NOT AVAILABLE">
          <div className="panel-empty">SELECTED DRIVERS ARE NOT ADJACENT ON TRACK — BATTLE RECOMMENDATION NOT APPLICABLE</div>
        </Panel>
      )}
      <Panel eyebrow="SHARED STRATEGY" title="Interaction">
        <div className="battle-offsets" style={{ display: "flex", flexDirection: "column", gap: "12px", padding: "16px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "var(--accent)", font: "700 9px/1 var(--mono)" }}>TYRE OFFSET</span>
            <strong style={{ font: "800 13px/1 var(--mono)" }}>{left?.tyre_age ?? "-"}L {left?.compound?.[0] ?? "-"} vs {right?.tyre_age ?? "-"}L {right?.compound?.[0] ?? "-"}</strong>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "var(--accent)", font: "700 9px/1 var(--mono)" }}>PACE (DEG)</span>
            <strong style={{ font: "800 13px/1 var(--mono)" }}>{leftPace?.degradation.value != null ? `${leftPace.degradation.value}s` : "-"} vs {rightPace?.degradation.value != null ? `${rightPace.degradation.value}s` : "-"}</strong>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "var(--accent)", font: "700 9px/1 var(--mono)" }}>PRIMARY PLAN</span>
            <strong style={{ font: "800 13px/1 var(--mono)" }}>{leftStrategy?.primaryStrategy.value ?? "-"} vs {rightStrategy?.primaryStrategy.value ?? "-"}</strong>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "var(--accent)", font: "700 9px/1 var(--mono)" }}>PIT WINDOW</span>
            <strong style={{ font: "800 13px/1 var(--mono)" }}>{leftStrategy?.pitWindow.value ? `L${leftStrategy.pitWindow.value[0]}-${leftStrategy.pitWindow.value[1]}` : "-"} vs {rightStrategy?.pitWindow.value ? `L${rightStrategy.pitWindow.value[0]}-${rightStrategy.pitWindow.value[1]}` : "-"}</strong>
          </div>
        </div>
      </Panel>
    </div>
  </div>;
}
