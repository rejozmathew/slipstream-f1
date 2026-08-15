import { useEffect, useMemo, useRef, useState } from "react";

import { StrategyOutlook } from "../components/analysis/StrategyOutlook";
import { TrackMap } from "../components/analysis/TrackMap";
import { BattleDriverCard } from "../components/battle/BattleDriverCard";
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

function driverTV(driver: Driver | null, analytics: AnalyticsSnapshot | null) {
  const model = driver ? analytics?.drivers[driver.number] : null;
  const samples = model?.pace.samples.slice(-22) ?? [];
  const latestPit = model?.pitEvents.at(-1) ?? null;
  return <div className="tv-driver-state">
    {!driver && <div className="unknown-block"><strong>DRIVER · NOT SELECTED</strong><p>Choose a Driver TV target in Settings → Preferences.</p></div>}
    {driver && <><header style={{ borderColor: `#${driver.team_colour ?? "77808f"}` }}><div><span>DRIVER FOCUS</span><strong>{driver.number}</strong></div><div><h2>{driver.name ?? driver.code ?? driver.number}</h2><p>{driver.team ?? "Team unavailable"}</p></div><b>P{driver.position ?? "—"}</b></header><div className="tv-driver-grid"><section><div><span>AHEAD</span><strong>{model?.ahead?.code ?? "—"}</strong><small>{model?.ahead?.gapSeconds == null ? "GAP UNKNOWN" : `${model.ahead.gapSeconds.toFixed(3)}s`}</small></div><div><span>BEHIND</span><strong>{model?.behind?.code ?? "—"}</strong><small>{model?.behind?.gapSeconds == null ? "GAP UNKNOWN" : `${model.behind.gapSeconds.toFixed(3)}s`}</small></div><div><span>TYRE / AGE</span><strong>{driver.compound ?? "—"} · {driver.tyre_age ?? "—"}L</strong></div><div><span>LAST / BEST</span><strong>{driver.last_lap ?? "—"} · {driver.best_lap ?? "—"}</strong></div><div><span>LAST PIT</span><strong>{latestPit ? `L${latestPit.lap} · ${latestPit.previousCompound?.[0] ?? "—"} → ${latestPit.newCompound?.[0] ?? "—"}` : "—"}</strong><small>{latestPit?.stopDuration == null ? "STOP UNKNOWN" : `STOP ${latestPit.stopDuration.toFixed(1)}s`}</small></div></section><div className="tv-driver-pace"><span>PACE DELTA · STINT TREND</span><div>{samples.map((sample) => <i key={`${sample.lap}-${sample.stintNumber}`} className={`quality-${sample.quality} compound-bar-${(sample.compound ?? "unknown").toLowerCase()}`} title={`Lap ${sample.lap} · ${sample.delta ?? "unknown"}s`} style={{ height: `${sample.delta == null ? 8 : Math.max(8, Math.min(90, Math.abs(sample.delta) * 34))}%` }} />)}</div></div><StrategyOutlook analytics={analytics} driverNumber={driver.number} compact /></div></>}
  </div>;
}

export function TVModeView({ state, analytics, recommendedBattle, sessionLayout, sessionKind, replayAvailable, positionMode, preferences, onPreferencesChange, onSelectDriver, onExit }: {
  state: RaceState;
  analytics: AnalyticsSnapshot | null;
  recommendedBattle: [string, string] | null;
  sessionLayout: SessionLayout;
  sessionKind: SessionKind;
  replayAvailable: boolean;
  positionMode: PositionMode;
  preferences: TVPreferences;
  onPreferencesChange: (value: TVPreferences) => void;
  onSelectDriver: (driverNumber: string) => void;
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
    queueMicrotask(() => {
      setScopedAlert(`SECTOR ${latestControl.sector ?? "—"} · ${latestControl.flag ?? "FLAG"}`);
      setStatusAlert(true);
    });
    const timer = window.setTimeout(() => {
      setScopedAlert(null);
      setStatusAlert(false);
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [latestControl?.occurred_at, latestControl?.flag, latestControl?.scope, latestControl?.sector, preferences.alertOnCriticalStatus]);

  const unavailableTitle = visibleState === "cutline" ? "Qualifying cutline" : visibleState === "sectors" ? "Sector evolution" : visibleState === "runs" ? "Practice runs" : visibleState === "pace" ? "Long-run pace" : "Stint context";
  return <div className={`tv-mode-view${statusAlert ? " tv-status-alert" : ""}`}>
    <header className="tv-header"><div className="tv-brand"><i>SS</i><span><strong>SLIPSTREAM</strong><small>TV MODE · {sessionKind.replaceAll("_", " ").toUpperCase()}</small></span></div><div className="tv-session"><span>{state.session.meeting_name ?? "Session unavailable"}</span><strong>{state.session.name ?? layout.toUpperCase()}</strong></div><div className="tv-status"><span>TRACK</span><strong data-track-status={state.session.track_status?.toLowerCase().replaceAll(" ", "-")}>{scopedAlert ?? state.session.track_status ?? "—"}</strong><span>LAP</span><b>{state.session.lap ?? "—"} / {state.session.total_laps ?? "—"}</b></div><button onClick={onExit}>EXIT TV</button></header>
    <main className={`tv-stage tv-stage-${visibleState}`}>
      {visibleState === "tower" && <div className="tv-tower"><TimingTower drivers={drivers} variant={layout === "race" ? "race" : layout === "qualifying" ? "qualifying" : "practice"} replayAvailable={replayAvailable} analytics={analytics} /></div>}
      {visibleState === "track" && <div className="tv-track"><TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} /></div>}
      {visibleState === "strategy" && <div className="tv-strategy"><StrategyOutlook analytics={analytics} driverNumber={selectedDriver?.number} /><div className="tv-insight-note"><span>SLIPSTREAM MODEL</span><strong>{analytics?.stage.replaceAll("_", " ") ?? "BASELINE AVAILABLE"}</strong><p>{analytics?.context.status === "preparing" ? "Weekend evidence is being prepared without interrupting replay." : "Every value identifies observed, derived, estimated, or insufficient evidence."}</p></div></div>}
      {visibleState === "battle" && <div className="tv-battle"><header><span>{preferences.battleMode.toUpperCase()} BATTLE</span><strong>{battle?.[0] && battle[1] ? `${battle[0].code ?? battle[0].number} · ${gapBetween(battle[0], battle[1])?.toFixed(3) ?? "—"}s · ${battle[1].code ?? battle[1].number}` : "NOT AVAILABLE"}</strong></header><div><BattleDriverCard driver={battle?.[0] ?? null} side="left" /><i /><BattleDriverCard driver={battle?.[1] ?? null} side="right" /></div></div>}
      {visibleState === "driver" && driverTV(selectedDriver, analytics)}
      {!(["tower", "track", "strategy", "battle", "driver"] as TVState[]).includes(visibleState) && <Panel eyebrow={layout.toUpperCase()} title={unavailableTitle} className="tv-unavailable-panel"><div className="unknown-block"><strong>ANALYTICS · UNKNOWN</strong><p>The current evidence does not yet support this authored state.</p></div></Panel>}
    </main>
    <footer className="tv-rotation"><div>{authoredStates.map((item, index) => <button className={visibleState === item ? "active" : ""} key={item} onClick={() => setActive(item)}><span>{String(index + 1).padStart(2, "0")}</span>{item.toUpperCase()}</button>)}</div><button className={rotating ? "rotation-toggle active" : "rotation-toggle"} onClick={() => setRotating((value) => !value)}>{rotating ? "AUTO ROTATION ON" : "AUTO ROTATION OFF"}</button><button className="tv-driver-shortcut" disabled={!selectedDriver} onClick={() => selectedDriver && onSelectDriver(selectedDriver.number)}>OPEN DRIVER</button><button className="tv-alert-toggle" onClick={() => onPreferencesChange({ ...preferences, alertOnCriticalStatus: !preferences.alertOnCriticalStatus })}>ALERTS {preferences.alertOnCriticalStatus ? "ON" : "OFF"}</button></footer>
  </div>;
}
