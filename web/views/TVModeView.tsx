import { useEffect, useMemo, useRef, useState } from "react";
import type React from "react";

import { PaceDeltaChart } from "../components/analysis/PaceDeltaChart";
import { StrategyOutlook } from "../components/analysis/StrategyOutlook";
import { TrackMap } from "../components/analysis/TrackMap";
import { CompoundBadge, CompoundTransition } from "../components/shared/CompoundBadge";
import { Panel } from "../components/shared/Panel";
import { TimingTower } from "../components/timing/TimingTower";
import { gapBetween } from "../domain/battle";
import type { AnalyticsSnapshot, Driver, PositionMode, RaceState, SessionKind } from "../domain/protocol";
import type { SessionLayout } from "../domain/sessionLayout";
import { isCriticalTrackStatus, nextAuthoredState } from "../domain/tvMode.mjs";
import type { TVPreferences, TVStatePreference } from "../hooks/useProductPreferences";

type TVState = TVStatePreference | "cutline" | "sectors" | "runs" | "pace" | "stints";

const stateSets: Record<Exclude<SessionLayout, "unsupported">, TVState[]> = {
  race: ["tower", "track", "strategy", "battle", "driver"],
  qualifying: ["tower", "cutline", "sectors", "track"],
  practice: ["tower", "runs", "pace", "stints"],
};

function statusTone(status?: string | null) {
  const value = status?.toLowerCase() ?? "unknown";
  if (value.includes("red")) return "red";
  if (value.includes("sc") || value.includes("safety") || value.includes("vsc")) return "safety";
  if (value.includes("yellow")) return "yellow";
  if (value.includes("green") || value.includes("clear")) return "green";
  return "unknown";
}

function DriverTV({ driver, analytics }: { driver: Driver | null; analytics: AnalyticsSnapshot | null }) {
  const model = driver ? analytics?.drivers[driver.number] : null;
  const samples = model?.pace.samples.slice(-22) ?? [];
  const latestPit = model?.pitEvents.at(-1) ?? null;
  if (!driver) return <div className="unknown-block"><strong>DRIVER · NOT SELECTED</strong><p>Choose a Driver TV target in Settings → Preferences.</p></div>;
  return <div className="tv-driver-state">
    <header style={{ borderColor: `#${driver.team_colour ?? "77808f"}` }}><div><span>DRIVER</span><strong>#{driver.number}</strong></div><div><h2>{driver.name ?? driver.code ?? driver.number}</h2><p>{driver.team ?? "Team unavailable"}</p></div><b>P{driver.position ?? "—"}</b></header>
    <div className="tv-driver-zones">
      <section className="tv-driver-facts"><h3>DRIVER STATE</h3><div><span>AHEAD</span><strong>{model?.ahead?.code ?? "—"}</strong><small>{model?.ahead?.gapSeconds == null ? "—" : `${model.ahead.gapSeconds.toFixed(3)}s`}</small></div><div><span>BEHIND</span><strong>{model?.behind?.code ?? "—"}</strong><small>{model?.behind?.gapSeconds == null ? "—" : `${model.behind.gapSeconds.toFixed(3)}s`}</small></div><div><span>TYRE / AGE</span><strong><CompoundBadge compound={driver.compound} compact /> {driver.tyre_age == null ? "—" : `${driver.tyre_age}L`}</strong></div><div><span>STRATEGY · DISPOSITION</span><strong>{model?.strategy.disposition ?? "—"}</strong><small>{model?.strategy.windowState ? `WINDOW ${model.strategy.windowState}` : "WINDOW —"}</small></div><div><span>LAST / BEST</span><strong>{driver.last_lap ?? "—"} · {driver.best_lap ?? "—"}</strong></div>{latestPit && <div><span>LATEST PIT · L{latestPit.lap}</span><strong><CompoundTransition from={latestPit.previousCompound} to={latestPit.newCompound} compact /></strong><small>STOP {latestPit.stopDuration == null ? "—" : `${latestPit.stopDuration.toFixed(1)}s`}</small></div>}</section>
      <section className="tv-driver-pace"><h3>PACE TREND</h3><PaceDeltaChart samples={samples} compact serverScale={model?.pace.scale} /></section>
      <StrategyOutlook analytics={analytics} driverNumber={driver.number} compact />
    </div>
  </div>;
}
function TVBattle({ drivers, analytics, mode }: { drivers: readonly [Driver | undefined, Driver | undefined] | null; analytics: AnalyticsSnapshot | null; mode: string }) {
  const left = drivers?.[0] ?? null;
  const right = drivers?.[1] ?? null;
  if (!left || !right) return <div className="unknown-block"><strong>BATTLE · NOT AVAILABLE</strong><p>No adjacent comparable pair is available.</p></div>;
  const isRecommended = mode.toUpperCase() === "RECOMMENDED";
  const gap = isRecommended && analytics?.battle.recommended ? gapBetween(left, right) : gapBetween(left, right);
  const trend = isRecommended ? analytics?.battle.gapTrend : undefined;
  const cards = [left, right];
  return <div className="tv-battle"><header><span>{mode.toUpperCase()} BATTLE</span><strong>{left.code ?? left.number} · {gap == null ? "—" : `${gap.toFixed(3)}s`} · {right.code ?? right.number}</strong></header><div className="tv-battle-grid">{cards.map((driver) => {
    const model = analytics?.drivers[driver.number];
    const window = model?.strategy.pitWindow.value;
    return <section key={driver.number} style={{ "--team": `#${driver.team_colour ?? "77808f"}` } as React.CSSProperties}><header><b>P{driver.position ?? "—"}</b><strong>{driver.code ?? driver.number}</strong><span>#{driver.number}</span></header><p>{driver.name ?? "Driver"} · {driver.team ?? "Team unavailable"}</p><div><span>TYRE / AGE</span><strong><CompoundBadge compound={driver.compound} compact /> {driver.tyre_age == null ? "—" : `${driver.tyre_age}L`}</strong></div><div><span>LAST / REPRESENTATIVE</span><strong>{driver.last_lap ?? "—"} · {model?.pace.currentStintBaseline?.toFixed(3) ?? "—"}</strong></div><div><span>STRATEGY WINDOW</span><strong>{window ? `L${window[0]}–${window[1]}` : "—"}</strong></div><div><span>UNDERCUT</span><strong>{model?.strategy.undercutStrength.value ?? "—"}</strong></div></section>;
  })}<div className="tv-battle-trend"><span>CURRENT GAP</span><strong>{gap == null ? "—" : `${gap.toFixed(3)}s`}</strong>{trend && <small className={`trend trend-${trend.toLowerCase()}`}>{trend}</small>}</div></div></div>;
}

function TVTrack({ state, drivers, analytics, positionMode, replayAvailable }: { state: RaceState; drivers: Driver[]; analytics: AnalyticsSnapshot | null; positionMode: PositionMode; replayAvailable: boolean }) {
  return <div className="tv-track-composed"><div className="tv-track-map"><TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} /></div><div className="tv-mini-tower"><TimingTower drivers={drivers.slice(0, 10)} variant="race" replayAvailable={replayAvailable} analytics={analytics} /></div></div>;
}
export function TVModeView({ state, analytics, recommendedBattle, sessionLayout, sessionKind, replayAvailable, positionMode, preferences, onPreferencesChange, onExit }: {
  state: RaceState;
  analytics: AnalyticsSnapshot | null;
  recommendedBattle: [string, string] | null;
  sessionLayout: SessionLayout;
  sessionKind: SessionKind;
  replayAvailable: boolean;
  positionMode: PositionMode;
  preferences: TVPreferences;
  onPreferencesChange: (value: TVPreferences) => void;
  onExit: () => void;
}) {
  const layout = sessionLayout === "unsupported" ? "race" : sessionLayout;
  const authoredStates = layout === "race" ? preferences.includedRaceStates.length ? preferences.includedRaceStates : stateSets.race : stateSets[layout];
  const [active, setActive] = useState<TVState>(authoredStates[0]);
  const [rotating, setRotating] = useState(false);
  const [statusAlert, setStatusAlert] = useState(false);
  const [scopedAlert, setScopedAlert] = useState<string | null>(null);
  const previousStatus = useRef(state.session.track_status);
  const drivers = useMemo(() => Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999)), [state.drivers]);
  const selectedDriver = drivers.find((driver) => driver.number === preferences.selectedDriverNumber) ?? drivers[0] ?? null;
  const leaderPair = drivers.length >= 2 ? [drivers[0].number, drivers[1].number] as [string, string] : null;
  const selectedPair = preferences.battleMode === "leader" ? leaderPair : preferences.battleMode === "pinned" ? preferences.pinnedBattle : recommendedBattle;
  const battle = selectedPair ? [drivers.find((driver) => driver.number === selectedPair[0]), drivers.find((driver) => driver.number === selectedPair[1])] as const : null;
  const visibleState = authoredStates.includes(active) ? active : authoredStates[0];

  useEffect(() => {
    if (!rotating) return;
    const timer = window.setInterval(() => setActive((current) => nextAuthoredState(authoredStates, current) ?? authoredStates[0]), Math.max(5, preferences.rotationIntervalSeconds) * 1000);
    return () => window.clearInterval(timer);
  }, [authoredStates, preferences.rotationIntervalSeconds, rotating]);

  useEffect(() => {
    const next = state.session.track_status;
    if (preferences.alertOnCriticalStatus && next !== previousStatus.current && isCriticalTrackStatus(next)) {
      queueMicrotask(() => setStatusAlert(true));
      const timer = window.setTimeout(() => setStatusAlert(false), 4000);
      previousStatus.current = next;
      return () => window.clearTimeout(timer);
    }
    previousStatus.current = next;
  }, [preferences.alertOnCriticalStatus, state.session.track_status]);

  const latestControl = state.race_control.at(-1) ?? null;
  useEffect(() => {
    if (!preferences.alertOnCriticalStatus || latestControl?.scope?.toLowerCase() !== "sector" || !isCriticalTrackStatus(latestControl.flag)) return;
    queueMicrotask(() => { setScopedAlert(`SECTOR ${latestControl.sector ?? "—"} · ${latestControl.flag ?? "FLAG"}`); setStatusAlert(true); });
    const timer = window.setTimeout(() => { setScopedAlert(null); setStatusAlert(false); }, 4000);
    return () => window.clearTimeout(timer);
  }, [latestControl?.occurred_at, latestControl?.flag, latestControl?.scope, latestControl?.sector, preferences.alertOnCriticalStatus]);

  const unavailableTitle = visibleState === "cutline" ? "Qualifying cutline" : visibleState === "sectors" ? "Sector evolution" : visibleState === "runs" ? "Practice runs" : visibleState === "pace" ? "Long-run pace" : "Stint context";
  const tone = statusTone(state.session.track_status);
  return <div className={`tv-mode-view${statusAlert ? " tv-status-alert" : ""}`} data-track-tone={tone}>
    <header className="tv-header"><div className="tv-brand"><i>SS</i><span><strong>SLIPSTREAM</strong><small>TV MODE · {sessionKind.replaceAll("_", " ").toUpperCase()}</small></span></div><div className="tv-session"><span>{state.session.meeting_name ?? "Session unavailable"}</span><strong>{state.session.name ?? layout.toUpperCase()}</strong></div><div className="tv-status"><span>LAP</span><b>{state.session.lap ?? "—"} / {state.session.total_laps ?? "—"}</b></div><button onClick={onExit}>EXIT TV</button></header>
    <div className={`tv-status-rail tv-status-${tone}${statusAlert ? " critical-transition" : ""}`}><span>{scopedAlert ?? state.session.track_status ?? "TRACK STATUS UNAVAILABLE"}</span></div>
    <main className={`tv-stage tv-stage-${visibleState}`}>
      {visibleState === "tower" && <div className="tv-tower"><TimingTower drivers={drivers} variant={layout === "race" ? "race" : layout === "qualifying" ? "qualifying" : "practice"} mode="standard" replayAvailable={replayAvailable} analytics={analytics} /></div>}
      {visibleState === "track" && (layout === "race" ? <TVTrack state={state} drivers={drivers} analytics={analytics} positionMode={positionMode} replayAvailable={replayAvailable} /> : <div className="tv-track"><TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} /></div>)}
      {visibleState === "strategy" && <div className="tv-strategy"><StrategyOutlook analytics={analytics} /><div className="tv-insight-note"><span>RACE-WIDE MODEL</span><strong>{analytics?.stage.replaceAll("_", " ") ?? "BASELINE AVAILABLE"}</strong><p>{analytics?.context.status === "preparing" ? "Weekend evidence is being prepared without interrupting replay." : "Field strategy is separate from every Driver-specific strategy and keeps insufficient evidence UNKNOWN."}</p></div></div>}
      {visibleState === "battle" && <TVBattle drivers={battle} analytics={analytics} mode={preferences.battleMode} />}
      {visibleState === "driver" && <DriverTV driver={selectedDriver} analytics={analytics} />}
      {!( ["tower", "track", "strategy", "battle", "driver"] as TVState[]).includes(visibleState) && <Panel eyebrow={layout.toUpperCase()} title={unavailableTitle} className="tv-unavailable-panel"><div className="unknown-block"><strong>ANALYTICS · UNKNOWN</strong><p>The current evidence does not yet support this authored state.</p></div></Panel>}
    </main>
    <footer className="tv-rotation"><div>{authoredStates.map((item, index) => <button className={visibleState === item ? "active" : ""} key={item} onClick={() => setActive(item)}><span>{String(index + 1).padStart(2, "0")}</span>{item.toUpperCase()}</button>)}</div><button className={rotating ? "rotation-toggle active" : "rotation-toggle"} onClick={() => setRotating((value) => !value)}>{rotating ? "AUTO ROTATION ON" : "AUTO ROTATION OFF"}</button><button className="tv-alert-toggle" onClick={() => onPreferencesChange({ ...preferences, alertOnCriticalStatus: !preferences.alertOnCriticalStatus })}>ALERTS {preferences.alertOnCriticalStatus ? "ON" : "OFF"}</button></footer>
  </div>;
}
