import { useMemo, useState } from "react";

import { BattleDriverCard } from "../components/battle/BattleDriverCard";
import { Panel } from "../components/shared/Panel";
import { currentPairGap, gapBetween } from "../domain/battle";
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
  const gap = currentPairGap(analytics, left, right);
  const samples: GapSample[] = !left || !right ? [] : stateHistory.flatMap((snapshot) => {
      const value = gapBetween(snapshot.drivers[left.number] ?? null, snapshot.drivers[right.number] ?? null);
      return snapshot.updated_at && value != null ? [{ at: snapshot.updated_at, value }] : [];
    });
  const trend = samples.length < 3 ? "INSUFFICIENT HISTORY" : samples.at(-1)!.value < samples[0].value - 0.05 ? "CLOSING" : samples.at(-1)!.value > samples[0].value + 0.05 ? "OPENING" : "STABLE";
  const battleCandidate = analytics?.battle.candidates.find((item) => item.aheadDriverNumber === left?.number && item.behindDriverNumber === right?.number) ?? null;
  const leftStrategy = left ? analytics?.drivers[left.number]?.strategy : null;
  const rightStrategy = right ? analytics?.drivers[right.number]?.strategy : null;
  const battleValid = Boolean(
    left?.position != null
    && right?.position != null
    && left.position != null && right.position != null
    && Math.abs(right.position - left.position) === 1
  );

  return <div className="battle-view">
    <header className="experience-heading"><div><span>RACE INTELLIGENCE</span><h1>Battle</h1><p>One deterministic recommendation shared by desktop and TV.</p></div><div className="battle-modes">{(["recommended", "leader", "pinned"] as const).map((item) => <button className={mode === item ? "active" : ""} key={item} onClick={() => setMode(item)}>{item.toUpperCase()}</button>)}</div></header>
    <div className="battle-selectors"><label><span>DRIVER A</span><select value={left?.number ?? pinned[0]} onChange={(event) => { setPinned([event.target.value, pinned[1]]); setMode("pinned"); }}>{drivers.map((driver) => <option key={driver.number} value={driver.number}>P{driver.position ?? "-"} · {driver.code ?? driver.number}</option>)}</select></label><div><span>OBSERVED GAP</span><strong>{gap == null ? "-" : `${gap.toFixed(3)}s`}</strong><small className={`trend trend-${trend.toLowerCase().split(" ")[0]}`}>{trend}</small></div><label><span>DRIVER B</span><select value={right?.number ?? pinned[1]} onChange={(event) => { setPinned([pinned[0], event.target.value]); setMode("pinned"); }}>{drivers.map((driver) => <option key={driver.number} value={driver.number}>P{driver.position ?? "-"} · {driver.code ?? driver.number}</option>)}</select></label></div>
    
    <div className="battle-symmetric">
      <BattleDriverCard driver={left} side="left" />
      <div className="battle-axis">
        <div style={{ height: "120px", width: "120px", border: "1px dashed #444", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "0.7rem", color: "#666", textAlign: "center" }}>
          TWO-DRIVER<br/>TRACK MAP
        </div>
      </div>
      <BattleDriverCard driver={right} side="right" />
    </div>
    
    <div className="battle-lower">
      <Panel eyebrow="LAST 5 COMPLETED LAPS" title="Gap history">
         <GapHistory samples={samples} />
      </Panel>
      
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
        <div className="battle-strategy-compare" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          {leftStrategy && rightStrategy && left && right ? (
             <div style={{ gridColumn: "1 / -1", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem" }}>
                  <span style={{ color: "var(--text-muted)", width: "120px" }}>TYRE OFFSET</span>
                  <strong style={{ flex: 1, textAlign: "center" }}>{(left.tyre_age ?? 0) - (right.tyre_age ?? 0)} laps</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem" }}>
                  <span style={{ color: "var(--text-muted)", width: "120px" }}>PACE DIFFERENCE</span>
                  <strong style={{ flex: 1, textAlign: "center" }}>{((leftStrategy.degradation?.value ?? 0) - (rightStrategy.degradation?.value ?? 0)).toFixed(3)} s/lap</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem" }}>
                  <span style={{ color: "var(--text-muted)", width: "120px" }}>RULE STATE</span>
                  <strong style={{ flex: 1, textAlign: "center" }}>{leftStrategy.dryTyreRequirement} vs {rightStrategy.dryTyreRequirement}</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem" }}>
                  <span style={{ color: "var(--text-muted)", width: "120px" }}>DISPOSITION</span>
                  <strong style={{ flex: 1, textAlign: "center" }}>{leftStrategy.disposition} vs {rightStrategy.disposition}</strong>
                </div>
             </div>
          ) : (
             <div className="panel-empty" style={{ gridColumn: "1 / -1" }}>NO MATERIAL STRATEGIC DIFFERENCE</div>
          )}
        </div>
      </Panel>
    </div>
  </div>;
}
