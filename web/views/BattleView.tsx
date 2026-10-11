import { useMemo } from "react";

import { BattlePublishedContext } from "../components/analysis/PublishedStrategy";
import { TrackMap } from "../components/analysis/TrackMap";
import { BattleDriverCard } from "../components/battle/BattleDriverCard";
import { BattleComposition } from "../components/battle/BattleComposition";
import { Panel } from "../components/shared/Panel";
import { battleFactorPresentation } from "../domain/correctness.mjs";
import { driverLifecycle } from "../domain/lifecycle";
import type { AnalyticsSnapshot, Driver, PositionMode, ViewingMode, RaceState } from "../domain/protocol";
import type { BattlePreferences } from "../hooks/useProductPreferences";

export function BattleView({ state, analytics, recommendedPair, positionMode, viewingMode, preferences, onPreferencesChange }: { state: RaceState; analytics: AnalyticsSnapshot | null; recommendedPair: [string, string] | null; positionMode: PositionMode; viewingMode: ViewingMode; preferences: BattlePreferences; onPreferencesChange: (value: BattlePreferences) => void }) {
  const drivers = useMemo(() => Object.values(state.drivers).filter((driver) => driverLifecycle(driver).battleEligible).sort((a, b) => (a.position ?? 999) - (b.position ?? 999)), [state.drivers]);
  const mode = preferences.mode;
  const pinned = preferences.pinnedPair;
  const setMode = (nextMode: BattlePreferences["mode"]) => onPreferencesChange({ ...preferences, mode: nextMode });
  const setPinned = (nextPair: [string, string]) => onPreferencesChange({ mode: "pinned", pinnedPair: nextPair });
  const recommended = recommendedPair ? [drivers.find((driver) => driver.number === recommendedPair[0]), drivers.find((driver) => driver.number === recommendedPair[1])] as const : null;
  const leaderPair = drivers.length >= 2 ? [drivers[0], drivers[1]] as [Driver, Driver] : null;
  const pinnedPair = [drivers.find((driver) => driver.number === pinned[0]) ?? null, drivers.find((driver) => driver.number === pinned[1]) ?? null] as const;
  const pair = mode === "recommended" ? recommended?.[0] && recommended[1] ? [recommended[0], recommended[1]] as [Driver, Driver] : null : mode === "leader" ? leaderPair : pinnedPair[0] && pinnedPair[1] && pinnedPair[0].number !== pinnedPair[1].number ? [pinnedPair[0], pinnedPair[1]] as [Driver, Driver] : null;
  const left = pair?.[0] ?? null;
  const right = pair?.[1] ?? null;
  const battleCandidate = analytics?.battle.candidates.find((item) => (item.aheadDriverNumber === left?.number && item.behindDriverNumber === right?.number) || (item.aheadDriverNumber === right?.number && item.behindDriverNumber === left?.number)) ?? null;

  return <div className="battle-view reference-battle-view">
    <header className="experience-heading"><div><span>RACE INTELLIGENCE</span><h1>Battle</h1><p>Recommended uses completed-lap source history; Leader and Pinned are your choice.</p></div><div className="battle-reference-controls"><div className="battle-modes">{(["recommended", "leader", "pinned"] as const).map((item) => <button className={mode === item ? "active" : ""} key={item} onClick={() => setMode(item)}>{item.toUpperCase()}</button>)}</div><label><span>DRIVER A</span><select value={left?.number ?? pinned[0]} onChange={(event) => setPinned([event.target.value, right?.number ?? pinned[1]])}><option value="">SELECT</option>{drivers.map((driver) => <option key={driver.number} value={driver.number} disabled={driver.number === right?.number}>P{driver.position ?? "—"} · {driver.code ?? driver.number}</option>)}</select></label><label><span>DRIVER B</span><select value={right?.number ?? pinned[1]} onChange={(event) => setPinned([left?.number ?? pinned[0], event.target.value])}><option value="">SELECT</option>{drivers.map((driver) => <option key={driver.number} value={driver.number} disabled={driver.number === left?.number}>P{driver.position ?? "—"} · {driver.code ?? driver.number}</option>)}</select></label></div></header>
    {pair && <BattleComposition state={state} analytics={analytics} pair={pair} />}
    {mode === "recommended" && !pair && <div className="service-unavailable battle-unavailable"><strong>NO STABILIZED MEANINGFUL BATTLE</strong><p>A recommendation appears from lap 3 in green running, after a known same-lap pair remains within 12 seconds across completed-lap source history.</p></div>}
    {mode === "pinned" && !pair && <div className="service-unavailable battle-unavailable"><strong>PINNED BATTLE UNAVAILABLE</strong><p>The selected pair is incomplete or no longer factually eligible. Choose a new pair to continue observing.</p></div>}
      {pair && <div className="battle-focus-grid"><BattleDriverCard driver={left} side="left" analytics={analytics} /><div className="battle-focused-map"><TrackMap circuit={state.circuit} session={state.session} drivers={Object.values(state.drivers)} positionMode={positionMode} viewingMode={viewingMode} focusedDriverNumbers={[left!.number, right!.number]} focusLabel={`${left!.code ?? left!.number} · ${right!.code ?? right!.number}`} /></div><BattleDriverCard driver={right} side="right" analytics={analytics} /></div>}
    <div className="battle-lower">
      <Panel eyebrow="BATTLE SCORE" title={battleCandidate ? `${battleCandidate.score.toFixed(1)} / 100` : "NOT AVAILABLE"}><div className="battle-score-factors">{battleCandidate?.factors.map((factor) => { const presentation = battleFactorPresentation(factor); return <div key={factor.name}><span>{presentation.contributionLabel}</span><strong>{presentation.contribution}</strong><small>{presentation.raw}</small></div>; }) ?? <div className="panel-empty">PAIR IS NOT A CURRENT MEANINGFUL BATTLE CANDIDATE</div>}</div></Panel>
      <Panel eyebrow="STRATEGY COMPARISON" title="Pirelli tyre strategy"><BattlePublishedContext analytics={analytics} drivers={left && right ? [left, right] : null} /></Panel>
    </div>
  </div>;
}

