import { useEffect, useMemo, useState } from "react";

import { StrategyOutlook } from "../components/analysis/StrategyOutlook";
import { TrackMap } from "../components/analysis/TrackMap";
import { BattleDriverCard } from "../components/battle/BattleDriverCard";
import { Panel } from "../components/shared/Panel";
import { TimingTower } from "../components/timing/TimingTower";
import { gapBetween, recommendedBattle } from "../domain/battle";
import type { PositionMode, RaceState } from "../domain/protocol";
import type { SessionLayout } from "../domain/sessionLayout";

type TVState = "tower" | "track" | "strategy" | "battle" | "cutline" | "sectors" | "runs" | "pace" | "stints";

const stateSets: Record<Exclude<SessionLayout, "unsupported">, TVState[]> = {
  race: ["tower", "track", "strategy", "battle"],
  qualifying: ["tower", "cutline", "sectors", "track"],
  practice: ["tower", "runs", "pace", "stints"],
};

export function TVModeView({ state, sessionLayout, replayAvailable, positionMode, onExit }: {
  state: RaceState;
  sessionLayout: SessionLayout;
  replayAvailable: boolean;
  positionMode: PositionMode;
  onExit: () => void;
}) {
  const layout = sessionLayout === "unsupported" ? "race" : sessionLayout;
  const authoredStates = stateSets[layout];
  const [active, setActive] = useState<TVState>(authoredStates[0]);
  const [rotating, setRotating] = useState(false);
  const drivers = useMemo(() => Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999)), [state.drivers]);
  const battle = recommendedBattle(drivers);

  useEffect(() => {
    if (!rotating) return;
    const timer = window.setInterval(() => setActive((current) => authoredStates[(authoredStates.indexOf(current) + 1) % authoredStates.length]), 12000);
    return () => window.clearInterval(timer);
  }, [authoredStates, rotating]);

  const unavailableTitle = active === "cutline" ? "Qualifying cutline" : active === "sectors" ? "Sector evolution" : active === "runs" ? "Practice runs" : active === "pace" ? "Long-run pace" : "Stint context";
  return <div className="tv-mode-view">
    <header className="tv-header"><div className="tv-brand"><i>SS</i><span><strong>SLIPSTREAM</strong><small>TV MODE · {layout.toUpperCase()}</small></span></div><div className="tv-session"><span>{state.session.meeting_name ?? "Session unavailable"}</span><strong>{state.session.name ?? layout.toUpperCase()}</strong></div><div className="tv-status"><span>TRACK</span><strong data-track-status={state.session.track_status?.toLowerCase().replaceAll(" ", "-")}>{state.session.track_status ?? "-"}</strong><span>LAP</span><b>{state.session.lap ?? "-"} / {state.session.total_laps ?? "-"}</b></div><button onClick={onExit}>EXIT TV</button></header>
    <main className={`tv-stage tv-stage-${active}`}>
      {active === "tower" && <div className="tv-tower"><TimingTower drivers={drivers} variant={layout === "race" ? "race" : layout === "qualifying" ? "qualifying" : "practice"} replayAvailable={replayAvailable} /></div>}
      {active === "track" && <div className="tv-track"><TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} /></div>}
      {active === "strategy" && <div className="tv-strategy"><StrategyOutlook /><div className="tv-insight-note"><span>PRODUCTION MODEL</span><strong>ANALYTICS NOT ENABLED</strong><p>This authored state remains ready for strategy without displaying prototype calculations.</p></div></div>}
      {active === "battle" && <div className="tv-battle"><header><span>RECOMMENDED BATTLE</span><strong>{battle ? `${battle[0].code ?? battle[0].number} · ${gapBetween(battle[0], battle[1])?.toFixed(3) ?? "-"}s · ${battle[1].code ?? battle[1].number}` : "NOT AVAILABLE"}</strong></header><div><BattleDriverCard driver={battle?.[0] ?? null} side="left" /><i /><BattleDriverCard driver={battle?.[1] ?? null} side="right" /></div></div>}
      {!(["tower", "track", "strategy", "battle"] as TVState[]).includes(active) && <Panel eyebrow={layout.toUpperCase()} title={unavailableTitle} className="tv-unavailable-panel"><div className="unknown-block"><strong>ANALYTICS NOT ENABLED</strong><p>The large-display composition is authored, but no derived values are invented until the production model exists.</p></div></Panel>}
    </main>
    <footer className="tv-rotation"><div>{authoredStates.map((item, index) => <button className={active === item ? "active" : ""} key={item} onClick={() => setActive(item)}><span>{String(index + 1).padStart(2, "0")}</span>{item.toUpperCase()}</button>)}</div><button className={rotating ? "rotation-toggle active" : "rotation-toggle"} onClick={() => setRotating((value) => !value)}>{rotating ? "AUTO ROTATION ON" : "AUTO ROTATION OFF"}</button></footer>
  </div>;
}
