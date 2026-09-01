import { useEffect, useMemo, useRef, useState } from "react";
import type React from "react";

import { PaceDeltaChart } from "../components/analysis/PaceDeltaChart";
import { DriverPirelliContext, PirelliBaseline, RaceNow, publishedWindowSummary } from "../components/analysis/PublishedStrategy";
import { TrackMap } from "../components/analysis/TrackMap";
import { CompoundBadge, CompoundTransition } from "../components/shared/CompoundBadge";
import { TimingTower } from "../components/timing/TimingTower";
import { completedLapGapTrend, currentPairGap } from "../domain/battle";
import { driverLifecycle } from "../domain/lifecycle";
import type { AnalyticsSnapshot, Driver, PositionMode, RaceState, SessionKind } from "../domain/protocol";
import type { SessionLayout } from "../domain/sessionLayout";
import { isCriticalTrackStatus, nextAuthoredState } from "../domain/tvMode.mjs";
import type { TVPreferences, TVStatePreference } from "../hooks/useProductPreferences";

type TVState = TVStatePreference;

const stateSets: Record<Exclude<SessionLayout, "unsupported">, TVState[]> = {
  race: ["tower", "track", "strategy", "battle", "driver"],
  qualifying: ["tower"],
  practice: ["tower"],
};

function statusTone(status?: string | null) {
  const value = status?.toLowerCase() ?? "unknown";
  if (value.includes("chequered") || value.includes("checkered")) return "chequered";
  if (value.includes("red")) return "red";
  if (value.includes("sc") || value.includes("safety") || value.includes("vsc")) return "safety";
  if (value.includes("yellow")) return "yellow";
  if (value.includes("green") || value.includes("clear")) return "green";
  return "unknown";
}

function DriverTV({ driver, analytics, state, positionMode }: {
  driver: Driver | null;
  analytics: AnalyticsSnapshot | null;
  state: RaceState;
  positionMode: PositionMode;
}) {
  const model = driver ? analytics?.drivers[driver.number] : null;
  const samples = model?.pace.samples.slice(-22) ?? [];
  const latestPit = model?.pitEvents.at(-1) ?? null;
  if (!driver) return <div className="unknown-block"><strong>DRIVER · NOT AVAILABLE</strong><p>No classified driver is available at this cursor.</p></div>;
  const lifecycle = driverLifecycle(driver);
  return <div className="tv-driver-state">
    <header style={{ borderColor: `#${driver.team_colour ?? "77808f"}` }}><div><span>DRIVER</span><strong>#{driver.number}</strong></div><div><h2>{driver.name ?? driver.code ?? driver.number}</h2><p>{driver.team ?? "Team unavailable"}</p>{lifecycle.label && <span className="driver-status-badge terminal">{lifecycle.label}</span>}</div><b>P{driver.position ?? "—"}</b></header>
    <div className="tv-driver-zones">
      <section className="tv-driver-facts"><h3>DRIVER STATE</h3><div><span>AHEAD</span><strong>{model?.ahead?.code ?? "—"}</strong><small>{model?.ahead?.gapSeconds == null ? "—" : `${model.ahead.gapSeconds.toFixed(3)}s`}</small></div><div><span>BEHIND</span><strong>{model?.behind?.code ?? "—"}</strong><small>{model?.behind?.gapSeconds == null ? "—" : `${model.behind.gapSeconds.toFixed(3)}s`}</small></div><div><span>TYRE / AGE</span><strong><CompoundBadge compound={driver.compound} compact /> {driver.tyre_age == null ? "—" : `${driver.tyre_age}L`}</strong></div><div><span>STINT / PITS</span><strong>{driver.stint_laps ?? "—"}L · {driver.pit_count}</strong></div><div><span>LAST / BEST</span><strong>{driver.last_lap ?? "—"} · {driver.best_lap ?? "—"}</strong></div>{latestPit && <div><span>LATEST PIT · L{latestPit.lap}</span><strong><CompoundTransition from={latestPit.previousCompound} to={latestPit.newCompound} compact /></strong><small>STOP {model?.pitEvents.length ?? driver.pit_count} · STATIONARY {latestPit.stopDuration == null ? "—" : `${latestPit.stopDuration.toFixed(1)}s`} · PIT LANE {latestPit.pitLaneDuration == null ? "—" : `${latestPit.pitLaneDuration.toFixed(1)}s`}</small></div>}<div className="tv-driver-read"><span>DRIVER READ</span><strong>{model?.read.headline ?? "Driver read not available yet."}</strong>{model?.read.facts.slice(0, 2).map((fact) => <small key={fact}>{fact}</small>)}</div></section>
      <div className="tv-driver-map"><TrackMap circuit={state.circuit} session={state.session} drivers={Object.values(state.drivers)} positionMode={positionMode} focusedDriverNumbers={[driver.number]} focusLabel={`${driver.code ?? driver.number} · FOCUS`} /></div>
      <div className="tv-driver-analysis"><section className="tv-driver-pace"><h3>PACE TREND</h3><PaceDeltaChart samples={samples} compact serverScale={model?.pace.scale} /></section><DriverPirelliContext analytics={analytics} driverNumber={driver.number} compact /></div>
    </div>
  </div>;
}

function BattleCard({ driver, analytics }: { driver: Driver; analytics: AnalyticsSnapshot | null }) {
  const model = analytics?.drivers[driver.number];
  const published = analytics?.publishedStrategy?.drivers[driver.number];
  const showPublished = analytics?.publishedStrategy?.status === "PRESENT";
  return <section className="tv-battle-card" style={{ "--team": `#${driver.team_colour ?? "77808f"}` } as React.CSSProperties}><header><b>P{driver.position ?? "—"}</b><strong>{driver.code ?? driver.number}</strong><span>#{driver.number}</span></header><p>{driver.name ?? "Driver"} · {driver.team ?? "Team unavailable"}</p><div><span>TYRE / AGE</span><strong><CompoundBadge compound={driver.compound} compact /> {driver.tyre_age == null ? "—" : `${driver.tyre_age}L`}</strong></div><div><span>LAST / REPRESENTATIVE</span><strong>{driver.last_lap ?? "—"} · {model?.pace.currentStintBaseline?.toFixed(3) ?? "—"}</strong></div>{showPublished && <><div><span>PIRELLI FIT</span><strong>{published?.relation.replaceAll("_", " ") ?? "—"}</strong></div><div><span>PUBLISHED WINDOWS</span><strong>{publishedWindowSummary(published, "—")}</strong></div></>}</section>;
}

function TVBattle({ drivers, analytics, mode, state, positionMode }: {
  drivers: readonly [Driver | undefined, Driver | undefined] | null;
  analytics: AnalyticsSnapshot | null;
  mode: string;
  state: RaceState;
  positionMode: PositionMode;
}) {
  const left = drivers?.[0] ?? null;
  const right = drivers?.[1] ?? null;
  if (!left || !right) return <div className="unknown-block"><strong>BATTLE · NOT AVAILABLE</strong><p>No adjacent comparable pair is available.</p></div>;
  const gap = currentPairGap(analytics, left, right);
  const historyKey = `${left.number}:${right.number}`;
  const reverseKey = `${right.number}:${left.number}`;
  const history = analytics?.battle.histories?.[historyKey] ?? analytics?.battle.histories?.[reverseKey] ?? [];
  const trend = completedLapGapTrend(history);
  return <div className="tv-battle"><header><span>{mode.toUpperCase()} BATTLE</span><strong>{left.code ?? left.number} · {gap == null ? "—" : `${gap.toFixed(3)}s`} · {right.code ?? right.number}</strong></header><div className="tv-battle-grid"><BattleCard driver={left} analytics={analytics} /><div className="tv-battle-map"><TrackMap circuit={state.circuit} session={state.session} drivers={Object.values(state.drivers)} positionMode={positionMode} focusedDriverNumbers={[left.number, right.number]} focusLabel={`${left.code ?? left.number} ↔ ${right.code ?? right.number}`} /><div className="tv-battle-trend"><span>COMPLETED-LAP TREND</span><strong>{trend.label}</strong><small>{trend.delta == null ? `${trend.sampleCount} SAMPLES` : `${trend.delta > 0 ? "+" : ""}${trend.delta.toFixed(3)}s · ${trend.sampleCount} LAPS`}</small></div></div><BattleCard driver={right} analytics={analytics} /></div></div>;
}

function TVTrack({ state, drivers, analytics, positionMode, replayAvailable }: { state: RaceState; drivers: Driver[]; analytics: AnalyticsSnapshot | null; positionMode: PositionMode; replayAvailable: boolean }) {
  return <div className="tv-track-composed"><div className="tv-track-map"><TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} /></div><div className="tv-mini-tower"><TimingTower drivers={drivers} variant="race" replayAvailable={replayAvailable} analytics={analytics} /></div></div>;
}

function hasRenderableCarPositions(drivers: Driver[], positionMode: PositionMode) {
  if (positionMode === "unavailable") return false;
  return drivers.some((driver) => positionMode === "precise_xy"
    ? driver.x != null && driver.y != null
    : driver.track_position != null);
}

export function TVModeView({ state, analytics, recommendedBattle, sessionLayout, sessionKind, replayAvailable, positionMode, sectorTimingAvailable, preferences, onPreferencesChange, onExit }: {
  state: RaceState;
  analytics: AnalyticsSnapshot | null;
  recommendedBattle: [string, string] | null;
  sessionLayout: SessionLayout;
  sessionKind: SessionKind;
  replayAvailable: boolean;
  positionMode: PositionMode;
  sectorTimingAvailable: boolean;
  preferences: TVPreferences;
  onPreferencesChange: (value: TVPreferences) => void;
  onExit: () => void;
}) {
  const layout = sessionLayout === "unsupported" ? "race" : sessionLayout;
  const qualifyingStates = useMemo<TVState[]>(() => {
    const items: TVState[] = ["tower"];
    if (state.circuit.path.length > 1 && hasRenderableCarPositions(Object.values(state.drivers), positionMode)) items.push("track");
    return items;
  }, [positionMode, state.circuit.path.length, state.drivers]);
  const authoredStates = useMemo(() => layout === "race" ? preferences.includedRaceStates.length ? preferences.includedRaceStates : stateSets.race : layout === "qualifying" ? qualifyingStates : stateSets.practice, [layout, preferences.includedRaceStates, qualifyingStates]);
  const [active, setActive] = useState<TVState>(authoredStates[0]);
  const [rotating, setRotating] = useState(false);
  const [statusAlert, setStatusAlert] = useState(false);
  const [scopedAlert, setScopedAlert] = useState<string | null>(null);
  const effectiveStatus = state.session.display_status && state.session.display_status !== "UNKNOWN"
    ? state.session.display_status
    : state.session.display_status == null && state.session.track_status && state.session.track_status !== "UNKNOWN"
      ? state.session.track_status
      : null;
  const previousStatus = useRef(effectiveStatus);
  const drivers = useMemo(() => Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999)), [state.drivers]);
  const selectedDriver = preferences.selectedDriverNumber
    ? drivers.find((driver) => driver.number === preferences.selectedDriverNumber) ?? null
    : drivers[0] ?? null;
  const battleDrivers = useMemo(() => drivers.filter((driver) => driverLifecycle(driver).battleEligible), [drivers]);
  const leaderPair = battleDrivers.length >= 2 ? [battleDrivers[0].number, battleDrivers[1].number] as [string, string] : null;
  const selectedPair = preferences.battleMode === "leader" ? leaderPair : preferences.battleMode === "pinned" ? preferences.pinnedBattle : recommendedBattle;
  const battle = selectedPair ? [battleDrivers.find((driver) => driver.number === selectedPair[0]), battleDrivers.find((driver) => driver.number === selectedPair[1])] as const : null;
  const visibleState = authoredStates.includes(active) ? active : authoredStates[0];

  useEffect(() => {
    if (!rotating) return;
    const timer = window.setInterval(() => setActive((current) => nextAuthoredState(authoredStates, current) ?? authoredStates[0]), Math.max(5, preferences.rotationIntervalSeconds) * 1000);
    return () => window.clearInterval(timer);
  }, [authoredStates, preferences.rotationIntervalSeconds, rotating]);

  useEffect(() => {
    const next = effectiveStatus;
    if (preferences.alertOnCriticalStatus && next && next !== previousStatus.current && isCriticalTrackStatus(next)) {
      queueMicrotask(() => setStatusAlert(true));
      const timer = window.setTimeout(() => setStatusAlert(false), 4000);
      previousStatus.current = next;
      return () => window.clearTimeout(timer);
    }
    previousStatus.current = next;
  }, [effectiveStatus, preferences.alertOnCriticalStatus]);

  const latestControl = state.race_control.at(-1) ?? null;
  useEffect(() => {
    if (!preferences.alertOnCriticalStatus || latestControl?.scope?.toLowerCase() !== "sector" || !isCriticalTrackStatus(latestControl.flag)) return;
    queueMicrotask(() => { setScopedAlert(`SECTOR ${latestControl.sector ?? "—"} · ${latestControl.flag ?? "FLAG"}`); setStatusAlert(true); });
    const timer = window.setTimeout(() => { setScopedAlert(null); setStatusAlert(false); }, 4000);
    return () => window.clearTimeout(timer);
  }, [latestControl?.occurred_at, latestControl?.flag, latestControl?.scope, latestControl?.sector, preferences.alertOnCriticalStatus]);

  const governingStatus = effectiveStatus?.replaceAll("_", " ") ?? (layout === "race" ? "STATUS —" : null);
  const tone = statusTone(governingStatus);
  const qualifyingPhase = analytics?.qualifying.phase && analytics.qualifying.phase !== "UNKNOWN" ? analytics.qualifying.phase : null;
  const qualifyingClock = analytics?.qualifying.sessionClock ?? null;
  const qualifyingFinal = layout === "qualifying" && analytics?.qualifying.final === true;
  const pirelliPresent = analytics?.publishedStrategy?.baseline.status === "PRESENT";
  return <div className={`tv-mode-view${statusAlert ? " tv-status-alert" : ""}`} data-track-tone={tone}>
    <header className="tv-header"><div className="tv-brand"><i>SS</i><span><strong>SLIPSTREAM</strong><small>TV MODE · {sessionKind.replaceAll("_", " ").toUpperCase()}</small></span></div><div className="tv-session"><span>{state.session.meeting_name ?? "Session unavailable"}</span><strong>{qualifyingFinal ? "QUALIFYING FINAL" : state.session.name ?? layout.toUpperCase()}</strong></div><div className="tv-status">{layout === "qualifying" ? <>{qualifyingPhase && <span>{qualifyingPhase}</span>}{qualifyingClock && <b>{qualifyingClock}</b>}</> : <><span>LAP</span><b>{state.session.lap ?? "—"} / {state.session.total_laps ?? "—"}</b></>}{governingStatus && <strong>{governingStatus}</strong>}</div><button onClick={onExit}>EXIT TV</button></header>
    <div className={`tv-status-rail ${governingStatus ? `tv-status-${tone}` : "tv-status-none"}${statusAlert ? " critical-transition" : ""}`}>{governingStatus && <span>{governingStatus}</span>}{scopedAlert && <small>{scopedAlert}</small>}</div>
    <main className={`tv-stage tv-stage-${visibleState}`}>
      {visibleState === "tower" && <div className="tv-tower"><TimingTower drivers={drivers} variant={layout === "race" ? "race" : layout === "qualifying" ? "qualifying" : "practice"} mode="standard" replayAvailable={replayAvailable} analytics={analytics} sectorTimingAvailable={layout === "qualifying" && sectorTimingAvailable} /></div>}
      {visibleState === "track" && (layout === "race" ? <TVTrack state={state} drivers={drivers} analytics={analytics} positionMode={positionMode} replayAvailable={replayAvailable} /> : <div className="tv-track"><TrackMap circuit={state.circuit} session={state.session} drivers={drivers} positionMode={positionMode} /></div>)}
      {visibleState === "strategy" && <div className={`tv-strategy pirelli-tv-strategy${pirelliPresent ? "" : " pirelli-tv-strategy-absent"}`}>{pirelliPresent ? <><PirelliBaseline baseline={analytics?.publishedStrategy?.baseline} /><RaceNow analytics={analytics} /></> : <><RaceNow analytics={analytics} /><PirelliBaseline baseline={analytics?.publishedStrategy?.baseline} compact /></>}</div>}
      {visibleState === "battle" && <TVBattle drivers={battle} analytics={analytics} mode={preferences.battleMode} state={state} positionMode={positionMode} />}
      {visibleState === "driver" && <DriverTV driver={selectedDriver} analytics={analytics} state={state} positionMode={positionMode} />}
    </main>
    <footer className="tv-rotation"><div>{authoredStates.map((item, index) => <button className={visibleState === item ? "active" : ""} key={item} onClick={() => setActive(item)}><span>{String(index + 1).padStart(2, "0")}</span>{item.toUpperCase()}</button>)}</div><button className={rotating ? "rotation-toggle active" : "rotation-toggle"} onClick={() => setRotating((value) => !value)}>{rotating ? "AUTO ROTATION ON" : "AUTO ROTATION OFF"}</button><button className="tv-alert-toggle" onClick={() => onPreferencesChange({ ...preferences, alertOnCriticalStatus: !preferences.alertOnCriticalStatus })}>ALERTS {preferences.alertOnCriticalStatus ? "ON" : "OFF"}</button></footer>
  </div>;
}

