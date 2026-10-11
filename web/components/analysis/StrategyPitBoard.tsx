import { driverLifecycle } from "../../domain/lifecycle";
import type { AnalyticsSnapshot, Driver, RaceState } from "../../domain/protocol";
import { CompoundTransition, normalizeCompound } from "../shared/CompoundBadge";
import { Panel } from "../shared/Panel";
import { storyTeamStyle } from "../story/presentation";

import "./strategy-presentation.css";

export type StrategyPitBoardProps = { state: RaceState; analytics: AnalyticsSnapshot | null; posture?: "desktop" | "tv"; onSelectDriver?: (driverNumber: string) => void };
const compoundNames: Record<string, string> = { SOFT: "SOFT", MEDIUM: "MEDIUM", HARD: "HARD", INTERMEDIATE: "INTER", WET: "WET", UNKNOWN: "UNKNOWN" };

export function StrategyPitBoard({ state, analytics, posture = "desktop", onSelectDriver }: StrategyPitBoardProps) {
  const field = Object.values(state.drivers).filter(driver => { const lifecycle = driverLifecycle(driver); return lifecycle.circulating || lifecycle.inPit; });
  const stops: Record<string, number> = {}, tyres: Record<string, number> = {};
  for (const driver of field) {
    const completed = analytics?.publishedStrategy?.drivers[driver.number]?.actualStrategy?.completedStops ?? (analytics?.drivers[driver.number]?.pitEvents ? analytics.drivers[driver.number].pitEvents.length : null);
    const count = completed == null ? "UNKNOWN" : String(Math.min(completed, 3));
    stops[count] = (stops[count] ?? 0) + 1;
    const compound = normalizeCompound(driver.compound) ?? "UNKNOWN";
    tyres[compound] = (tyres[compound] ?? 0) + 1;
  }
  const inLane = field.filter(driver => driverLifecycle(driver).inPit);
  const latest = Object.values(analytics?.drivers ?? {}).flatMap(driver => driver.pitEvents ?? []).sort((a, b) => Date.parse(b.occurredAt) - Date.parse(a.occurredAt) || b.sequence - a.sequence).slice(0, posture === "tv" ? 6 : 5);
  const driverButton = (driver: Driver) => <button key={driver.number} onClick={() => onSelectDriver?.(driver.number)} style={storyTeamStyle(driver)}><i />{driver.code ?? driver.number}</button>;
  return <div className={`strategy-pit-board strategy-pit-board-${posture}`}>
    <section><h3>STOPS COMPLETED</h3><div className="spb-bar">{["0", "1", "2", "3", "UNKNOWN"].filter(key => stops[key]).map(key => <i key={key} className={`spb-stops-${key.toLowerCase()}`} style={{ flex: stops[key] }}><b>{stops[key]}</b><em>{key === "UNKNOWN" ? "UNKNOWN" : `${key === "3" ? "3+" : key} STOP${key === "1" ? "" : "S"}`}</em></i>)}</div></section>
    <section><h3>TYRES ON CAR NOW</h3><div className="spb-bar">{Object.keys(compoundNames).filter(key => tyres[key]).map(key => <i key={key} className={`spb-compound-${key.toLowerCase()}`} style={{ flex: tyres[key] }}><b>{tyres[key]}</b><em>{compoundNames[key]}</em></i>)}</div></section>
    <section className="spb-lane"><h3>IN THE PIT LANE NOW</h3><div>{inLane.length ? inLane.map(driverButton) : <span>Empty</span>}</div></section>
    <section><h3>LATEST COMPLETED STOPS</h3><ol className="spb-stops">{latest.map(event => <li key={`${event.driverNumber}:${event.sequence}`} style={storyTeamStyle(state.drivers[event.driverNumber])}><span>L{event.lap}</span><button onClick={() => onSelectDriver?.(event.driverNumber)}>{state.drivers[event.driverNumber]?.code ?? event.driverNumber}</button><CompoundTransition from={event.previousCompound} to={event.newCompound} compact /><strong>{event.pitLaneDuration == null ? "—" : `${event.pitLaneDuration.toFixed(1)}s`}</strong><small>{event.pitLaneDuration == null ? "LANE TIME UNKNOWN" : "PIT LANE"}</small></li>)}</ol>{!latest.length && <p className="spb-empty">No completed stops yet</p>}</section>
    <p className="spb-note">Pit-lane time is the full lane transit from timing, not stationary time.</p>
  </div>;
}

export function observedStintSegments(driver: Driver, analytics: AnalyticsSnapshot | null, currentLap: number) {
  const actual = analytics?.publishedStrategy?.drivers[driver.number]?.actualStrategy;
  if (!actual) return [];
  const terminal = driverLifecycle(driver).terminal || driverLifecycle(driver).stopped || driverLifecycle(driver).retiredIndicated;
  const end = terminal ? Math.min(currentLap, driver.lap ?? 0) : Math.min(currentLap, driver.lap ?? currentLap);
  return actual.compounds.flatMap((compound, index) => {
    // An incomplete first stint has no proven start boundary. Later segments
    // can still be drawn between explicitly observed completed stops.
    const start = index === 0 ? actual.evidenceComplete ? 0 : null : actual.stopLaps[index - 1];
    const finish = index < actual.stopLaps.length ? actual.stopLaps[index] : end;
    if (start == null || finish == null || finish <= start || start > end) return [];
    return [{ compound: normalizeCompound(compound), start, end: Math.min(finish, end), index }];
  });
}

export function StrategyStintChart({ state, analytics, onSelectDriver }: StrategyPitBoardProps) {
  const drivers = Object.values(state.drivers).sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  const currentLap = state.session.lap ?? 0;
  const total = Math.max(1, state.session.total_laps ?? currentLap);
  const ticks = Array.from({ length: Math.floor(total / 10) + 1 }, (_, index) => index * 10);
  return <Panel eyebrow="FROM TIMING" title="Stints by lap" className="strategy-stints" action={<span className="stc-progress">lap {currentLap} of {state.session.total_laps ?? "—"}</span>}><div className="strategy-stint-chart"><div className="stc-current" style={{ left: `calc(98 * var(--st-unit) + (100% - 112 * var(--st-unit)) * ${Math.min(1, currentLap / total)})` }} />{drivers.map(driver => {
    const segments = observedStintSegments(driver, analytics, currentLap);
    const stops = analytics?.publishedStrategy?.drivers[driver.number]?.actualStrategy?.stopLaps ?? [];
    return <button className={`stc-driver${driverLifecycle(driver).terminal && driver.classification !== "FINISHED" ? " is-out" : ""}`} key={driver.number} onClick={() => onSelectDriver?.(driver.number)}><span>{driver.position ?? "—"}</span><b>{driver.code ?? driver.number}</b><span className="stc-bar">{segments.map(segment => <i className={`stc-${segment.compound?.toLowerCase() ?? "unknown"}`} key={segment.index} style={{ left: `${segment.start / total * 100}%`, width: `${(segment.end - segment.start) / total * 100}%` }} title={`${segment.compound ?? "UNKNOWN"} · laps ${segment.start}–${segment.end}`} />)}{stops.filter((lap): lap is number => lap != null && lap <= currentLap).map((lap, index) => <s key={index} style={{ left: `${lap / total * 100}%` }} />)}{!segments.length && <em>Stint history unavailable</em>}</span></button>;
  })}<div className="stc-axis"><span /><div>{ticks.map(lap => <em key={lap} style={{ left: `${lap / total * 100}%` }}>{lap}</em>)}</div></div></div></Panel>;
}
