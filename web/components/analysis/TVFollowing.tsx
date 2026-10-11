import type { CSSProperties } from "react";
import type { AnalyticsSnapshot, Driver, PaceSample, PositionMode, RaceState, ViewingMode } from "../../domain/protocol";
import { actualStrategyCompounds, dryTyreRequirementText } from "../../domain/pirelliPresentation.mjs";
import { driverLifecycle } from "../../domain/lifecycle";
import { CompoundBadge, CompoundSequence } from "../shared/CompoundBadge";
import { storyDriverName, storyLapTime, storyTeamStyle } from "../story/presentation";
import { TrackMap } from "./TrackMap";
import "./tv-following.css";

export function ObservedLapBars({ samples }: { samples: PaceSample[] }) {
  const stint = samples.at(-1)?.stintNumber;
  const current = samples.filter(sample => sample.stintNumber === stint).slice(-12);
  const clean = current.filter(sample => sample.quality === "representative" && sample.rawLapTime != null);
  const best = clean.length ? Math.min(...clean.map(sample => sample.rawLapTime!)) : null;
  return <section className="ref-laps"><h3>LAP TIMES THIS STINT</h3>{!current.length ? <p className="ref-muted">No completed laps yet.</p> : <><div className="ref-lap-bars">{current.map(sample => {
    const pit = sample.contaminationReasons.some(reason => /pit/i.test(reason));
    const height = best != null && sample.rawLapTime != null && sample.quality === "representative" ? Math.max(8, Math.min(100, (1 - (sample.rawLapTime - best) / 1.5) * 100)) : 10;
    return <div className={`ref-lap-bar${pit ? " is-pit" : best != null && sample.quality === "representative" && sample.rawLapTime === best ? " is-best" : ""}`} key={sample.lap} style={{ "--bar-height": `${height}%` } as CSSProperties}><i /><em>{pit ? "PIT" : storyLapTime(sample.rawLapTime) || "—"}</em><span>L{sample.lap}</span></div>;
  })}</div><p className="ref-muted">Taller = faster{best != null ? `, scaled from ${storyLapTime(best)} (best clean lap) to +1.5s.` : "."} In-laps and out-laps marked PIT.</p></>}</section>;
}

export function TVFollowing({ driver, analytics, state, positionMode, viewingMode }: { driver: Driver | null; analytics: AnalyticsSnapshot | null; state: RaceState; positionMode: PositionMode; viewingMode: ViewingMode }) {
  if (!driver) return <div className="unknown-block"><strong>FOLLOWING</strong><p>Choose a driver in the TV controls.</p></div>;
  const model = analytics?.drivers[driver.number];
  const published = analytics?.publishedStrategy?.drivers[driver.number];
  const latestPit = model?.pitEvents.at(-1);
  const lifecycle = driverLifecycle(driver);
  const events = (analytics?.story?.events ?? []).filter(event => event.driverNumbers.includes(driver.number)).slice(-2).reverse();
  const focus = [model?.ahead?.driverNumber, driver.number, model?.behind?.driverNumber].filter((number): number is string => !!number);
  return <div className="ref-tv-following" style={storyTeamStyle(driver)}><section className="ref-driver-card"><header><b>P{driver.position ?? "—"}</b><div><strong>{driver.code ?? driver.number}</strong><span>{storyDriverName(driver.number, state.drivers).surname} · {driver.team ?? "—"}</span></div>{lifecycle.label && <em>{lifecycle.label}</em>}</header><div className="ref-driver-facts">
    <div><h3>TO CAR AHEAD</h3><b>{model?.ahead?.gapSeconds == null ? "—" : `+${model.ahead.gapSeconds.toFixed(3)}`}</b><small>{model?.ahead?.code ?? "—"}</small></div>
    <div><h3>TO CAR BEHIND</h3><b>{model?.behind?.gapSeconds == null ? "—" : `+${model.behind.gapSeconds.toFixed(3)}`}</b><small>{model?.behind?.code ?? "—"}</small></div>
    <div><h3>TYRE</h3><b><CompoundBadge compound={driver.compound} compact /> {driver.tyre_age == null ? "—" : `${driver.tyre_age}L`}</b>{driver.tyre_usage !== "UNKNOWN" && <small>{driver.tyre_usage === "NEW" ? "new set" : "used set"}</small>}</div>
    <div><h3>STOPS</h3><b>{published?.actualStrategy.completedStops ?? "—"}</b></div>
    <div><h3>LAST LAP</h3><b>{driver.last_lap ?? "—"}</b></div><div><h3>BEST LAP</h3><b>{driver.best_lap ?? "—"}</b></div>
    <div><h3>CURRENT SECTORS</h3><span className="ref-sectors">{[driver.sector_1, driver.sector_2, driver.sector_3].map((value, index) => <b key={index}>{value?.toFixed(3) ?? "—"}</b>)}</span></div>
    <div><h3>TYRE STRATEGY</h3><CompoundSequence compounds={actualStrategyCompounds(published)} /><small>{dryTyreRequirementText(published) ?? ""}</small></div>
    <div className="ref-last-pit"><h3>LATEST PIT</h3><b>{latestPit ? `L${latestPit.lap} · ${latestPit.pitLaneDuration?.toFixed(1) ?? "—"}s` : "—"}</b><small>pit lane · stationary {latestPit?.stopDuration == null ? "not in timing" : `${latestPit.stopDuration.toFixed(1)}s`}</small></div>
  </div><ul className="ref-driver-events">{events.map(event => <li key={event.id}><span>{event.lap == null ? "" : `L${event.lap}`}</span><div><b>{event.title}</b><p>{event.detail}</p></div></li>)}</ul></section><div className="ref-following-right"><div className="ref-following-map">{positionMode === "unavailable" ? <div className="ref-map-unavailable"><b>No car positions</b><span>Order and gaps from timing only.</span></div> : <TrackMap posture="tv" showRibbon={false} circuit={state.circuit} session={state.session} drivers={Object.values(state.drivers)} positionMode={positionMode} viewingMode={viewingMode} focusedDriverNumbers={focus} focusLabel={`${driver.code ?? driver.number} · FOCUS`} />}</div><ObservedLapBars samples={model?.pace.samples ?? []} /></div></div>;
}
