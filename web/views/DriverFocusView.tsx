import { useMemo, type CSSProperties } from "react";

import { PaceDeltaChart } from "../components/analysis/PaceDeltaChart";
import { DriverPirelliContext } from "../components/analysis/PublishedStrategy";
import { TrackMap } from "../components/analysis/TrackMap";
import { CompoundBadge, CompoundTransition } from "../components/shared/CompoundBadge";
import { DataValue } from "../components/shared/DataValue";
import { InfoPopover } from "../components/shared/InfoPopover";
import { Panel } from "../components/shared/Panel";
import { formatLapTime, formatSector } from "../domain/format";
import { driverLifecycle } from "../domain/lifecycle";
import type { AnalyticsSnapshot, Driver, DriverBattleContext, DriverHistory, PaceSample, PitEvent, PositionMode, RaceState } from "../domain/protocol";
import type { SessionLayout } from "../domain/sessionLayout";

function BattleContext({ label, value }: { label: string; value: DriverBattleContext | null }) {
  if (!value) return <div><span>{label}</span><strong>—</strong></div>;
  return <div><span>{label}</span><strong>{value.code ?? value.driverNumber} · P{value.position ?? "—"}</strong><small>{value.gapSeconds == null ? "—" : `${value.gapSeconds.toFixed(3)}s`}</small></div>;
}

function PitHistory({ events }: { events: PitEvent[] }) {
  if (events.length === 0) return <div className="panel-empty">NO OBSERVED PIT EVENTS AT THIS REPLAY TIME</div>;
  const hasStationaryDuration = events.some((event) => event.stopDuration != null);
  const hasPitLaneDuration = events.some((event) => event.pitLaneDuration != null);
  const durationColumns = [hasStationaryDuration && "stationary", hasPitLaneDuration && "pit-lane"].filter(Boolean).join("-") || "none";
  return <><div className="pit-history-summary"><strong>{events.length}</strong><span>OBSERVED STOPS</span><small>Same-compound changes remain factual stops.</small></div><div className={`pit-history-list pit-history-columns-${durationColumns}`}>{events.map((event, index) => <div key={`${event.sequence}-${event.lap}`}>
    <span><small>STOP</small><b>{event.ordinal ?? index + 1}</b></span>
    <strong>LAP {event.lap}</strong>
    <CompoundTransition from={event.previousCompound} to={event.newCompound} compact />
    {hasStationaryDuration && <span><small>STATIONARY</small><b>{event.stopDuration == null ? "—" : `${event.stopDuration.toFixed(1)}s`}</b></span>}
    {hasPitLaneDuration && <span><small>PIT LANE</small><b>{event.pitLaneDuration == null ? "—" : `${event.pitLaneDuration.toFixed(1)}s`}</b></span>}
  </div>)}</div></>;
}

function QualifyingDriverFocus({ driver, state, analytics, positionMode, onChangeDriver, onBack }: {
  driver: Driver;
  state: RaceState;
  analytics: AnalyticsSnapshot | null;
  positionMode: PositionMode;
  onChangeDriver: () => void;
  onBack: () => void;
}) {
  const intelligence = analytics?.qualifying;
  const model = intelligence?.drivers[driver.number];
  const delta = model?.benchmarkDelta == null ? "—" : model.benchmarkDelta === 0 ? "BENCHMARK" : `+${model.benchmarkDelta.toFixed(3)}s`;
  const qualifierTitle = intelligence?.phase && intelligence.phase !== "UNKNOWN" ? `QUALIFYING · ${intelligence.phase}` : "QUALIFYING";
  const teammate = model?.teammate;
  const segmentLabels = analytics?.sessionKind === "sprint_qualifying" ? ["SQ1", "SQ2", "SQ3"] : ["Q1", "Q2", "Q3"];
  const segmentResults = model?.segmentResults ?? driver.qualifying_results ?? [null, null, null];
  return <div className="driver-focus-view qualifying-driver-focus">
    <header className="driver-hero" style={{ "--team": `#${driver.team_colour ?? "77808f"}` } as CSSProperties}>
      <div className="driver-hero-actions"><button onClick={onBack}>BACK</button><button onClick={onChangeDriver}>CHANGE DRIVER</button></div>
      <div className="driver-number">#{driver.number}</div>
      <div className="driver-identity"><span>{qualifierTitle}</span><h1>{driver.name ?? driver.code ?? driver.number}</h1><p>{driver.team ?? "Team unavailable"}</p></div>
      <div className="driver-hero-position"><span>CLASSIFICATION</span><strong>P{driver.position ?? "—"}</strong><DataValue compact value={delta} /></div>
    </header>
    <div className="qualifying-driver-grid">
      <Panel eyebrow="CURRENT QUALIFYING STATE" title="Driver facts" className="qualifying-driver-state"><div className="qualifying-driver-facts"><div><span>BEST</span><strong>{model?.scopeBest ?? driver.best_lap ?? driver.last_lap ?? "—"}</strong></div><div><span>GAP TO FASTEST</span><strong>{delta}</strong></div>{segmentLabels.map((label, index) => <div key={label}><span>{label}</span><strong>{formatLapTime(segmentResults[index])}</strong></div>)}<div><span>TYRE</span><strong><CompoundBadge compound={driver.compound} showLabel /></strong></div><div><span>AGE / USAGE</span><strong>{driver.tyre_age == null ? "—" : `${driver.tyre_age}L`} · {model?.tyreUsage === "UNKNOWN" ? "—" : model?.tyreUsage ?? "—"}</strong></div><div><span>Q STATUS</span><strong>{model?.qStatus ?? "—"}</strong></div><div><span>TEAMMATE</span><strong>{teammate ? `${teammate.code ?? teammate.driverNumber} · ${teammate.comparison}${teammate.gapSeconds == null ? "" : ` ${teammate.gapSeconds.toFixed(3)}s`}` : "—"}</strong></div></div></Panel>
      <Panel eyebrow="COMPLETED LAPS" title="QUALIFYING LAP HISTORY" className="qualifying-driver-attempts">{!model?.attempts.length && <div className="panel-empty">NO QUALIFYING LAPS RECORDED YET</div>}<div className="driver-attempt-list">{model?.attempts.map((lap) => <div key={`${lap.attempt}-${lap.occurredAt}`}><header>{lap.phase !== "UNKNOWN" && <span>{lap.phase}</span>}<b>LAP {lap.lap ?? "—"} · {lap.classification.replace("_", "-")}</b></header><div><strong>{formatLapTime(lap.lapTime)}</strong><span>S1 {formatSector(lap.sector1)}</span><span>S2 {formatSector(lap.sector2)}</span><span>S3 {formatSector(lap.sector3)}</span><CompoundBadge compound={lap.compound} compact /><em>{lap.tyreAge == null ? "—" : `${lap.tyreAge}L`} · {lap.tyreUsage === "UNKNOWN" ? "—" : lap.tyreUsage}</em></div></div>)}</div></Panel>
      <div className="qualifying-driver-map"><TrackMap circuit={state.circuit} session={state.session} drivers={Object.values(state.drivers)} positionMode={positionMode} focusedDriverNumbers={[driver.number]} focusLabel={driver.code ?? driver.number} /></div>
    </div>
  </div>;
}

export function DriverFocusView({ state, analytics, sessionLayout, driverNumber, history, historyError, playhead, positionMode, onChangeDriver, onBack }: {
  state: RaceState;
  analytics: AnalyticsSnapshot | null;
  sessionLayout: SessionLayout;
  driverNumber: string;
  history: DriverHistory | null;
  historyError: string | null;
  playhead: string | null;
  positionMode: PositionMode;
  onChangeDriver: () => void;
  onBack: () => void;
}) {
  const driver = state.drivers[driverNumber] ?? null;
  const model = analytics?.drivers[driverNumber] ?? null;
  const observations = useMemo(() => (history?.observations ?? []).filter((item) => !playhead || Date.parse(item.occurredAt) <= Date.parse(playhead)), [history?.observations, playhead]);
  const fallbackPits = useMemo(() => (history?.pitEvents ?? []).filter((item) => !playhead || Date.parse(item.occurredAt) <= Date.parse(playhead)), [history?.pitEvents, playhead]);
  const paceSamples = model?.pace.samples ?? observations.map((lap): PaceSample => ({ lap: lap.lap, rawLapTime: lap.duration, delta: null, compound: lap.compound, tyreAge: lap.tyre_age, stintNumber: lap.stint_number, quality: lap.quality, contaminationReasons: lap.contamination_reasons }));
  const pitEvents: PitEvent[] = model?.pitEvents ?? fallbackPits;
  if (!driver) return <div className="driver-focus-view"><header className="experience-heading"><button onClick={onBack}>BACK TO SESSION</button><div><span>DRIVER FOCUS</span><h1>Driver unavailable</h1></div></header><div className="service-unavailable"><strong>DRIVER STATE UNAVAILABLE</strong><p>This driver is not present at the current replay time.</p><button onClick={onChangeDriver}>CHOOSE DRIVER</button></div></div>;
  if (sessionLayout === "qualifying") return <QualifyingDriverFocus driver={driver} state={state} analytics={analytics} positionMode={positionMode} onChangeDriver={onChangeDriver} onBack={onBack} />;
  const allDrivers = Object.values(state.drivers);
  const lifecycle = driverLifecycle(driver);
  return <div className="driver-focus-view">
    <header className="driver-hero" style={{ "--team": `#${driver.team_colour ?? "77808f"}` } as CSSProperties}>
      <div className="driver-hero-actions"><button onClick={onBack}>BACK</button><button onClick={onChangeDriver}>CHANGE DRIVER</button></div>
      <div className="driver-number">#{driver.number}</div>
      <div className="driver-identity"><span>DRIVER FOCUS · LAP {driver.lap ?? state.session.lap ?? "—"}</span><h1>{driver.name ?? driver.code ?? `Driver ${driver.number}`}</h1><p>{driver.team ?? "Team unavailable"}</p>{lifecycle.label && <b className={"driver-status-badge " + (lifecycle.terminal ? "terminal" : "stopped")}>{lifecycle.label}</b>}</div>
      <div className="driver-hero-position"><span>CURRENT POSITION</span><strong>P{driver.position ?? "—"}</strong><DataValue compact value={driver.position === 1 ? "LEADER" : driver.gap_to_leader} availability={driver.availability.gap_to_leader} /></div>
    </header>
    <div className="driver-focus-grid">
      <section className="driver-current panel"><header className="panel-heading"><div className="panel-title"><h2>Current stint</h2><span className="eyebrow">FACTUAL</span></div></header>
        <div className="driver-current-metrics"><div><span>COMPOUND</span><strong><CompoundBadge compound={driver.compound} showLabel /></strong></div><div><span>TYRE AGE</span><strong>{driver.tyre_age == null ? "—" : `${driver.tyre_age} LAPS`}</strong></div><div><span>STINT LAPS</span><strong>{driver.stint_laps ?? "—"}</strong></div><div><span>PIT STOPS</span><strong>{driver.pit_count}</strong></div><div><span>LAST LAP</span><DataValue compact value={driver.last_lap} availability={driver.availability.last_lap} /></div><div><span>BEST LAP</span><DataValue compact value={driver.best_lap} availability={driver.availability.best_lap} /></div></div>
        <div className="driver-battle-context"><BattleContext label="AHEAD" value={model?.ahead ?? null} /><BattleContext label="BEHIND" value={model?.behind ?? null} /></div><div className="driver-read"><span>DRIVER READ</span><strong>{model?.read.headline ?? "Driver read not available yet."}</strong>{model?.read.facts.map((fact) => <p key={fact}>{fact}</p>)}</div>
      </section>
      <div className="driver-map-context"><TrackMap circuit={state.circuit} session={state.session} drivers={allDrivers} positionMode={positionMode} focusedDriverNumbers={[driverNumber]} focusLabel={driver.code ?? driver.number} /></div>
      <DriverPirelliContext analytics={analytics} driver={driver} />
      <Panel eyebrow="PACE DELTA" title="Stint trend" className="driver-history-panel" action={<span className="pace-baseline-badge">VS CLEAN STINT BASELINE <InfoPopover meaning="Signed lap-time delta versus the robust median of representative laps in the same stint. Faster laps are above zero; slower laps are below." why="Pit, neutralized, contaminated, and robust outlier laps do not set the chart scale. They remain visible as capped grey hatched markers." /></span>}>
        {historyError && <div className="panel-empty">HISTORY UNAVAILABLE · {historyError}</div>}
        {!historyError && !history && !model && <div className="panel-empty">LOADING NORMALIZED LAP EVIDENCE</div>}
        <PaceDeltaChart samples={paceSamples} serverScale={model?.pace.scale} />
      </Panel>
      <Panel eyebrow="FACTUAL" title="Pit history" className="pit-history-panel"><PitHistory events={pitEvents} /></Panel>
    </div>
  </div>;
}

