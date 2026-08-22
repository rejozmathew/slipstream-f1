import { useMemo, type CSSProperties } from "react";

import { PaceDeltaChart } from "../components/analysis/PaceDeltaChart";
import { StrategyOutlook } from "../components/analysis/StrategyOutlook";
import { TrackMap } from "../components/analysis/TrackMap";
import { CompoundBadge, CompoundTransition } from "../components/shared/CompoundBadge";
import { DataValue } from "../components/shared/DataValue";
import { InfoPopover } from "../components/shared/InfoPopover";
import { Panel } from "../components/shared/Panel";
import { driverLifecycle } from "../domain/lifecycle";
import type { AnalyticsSnapshot, DriverBattleContext, DriverHistory, PaceSample, PitEvent, PositionMode, RaceState } from "../domain/protocol";

function BattleContext({ label, value }: { label: string; value: DriverBattleContext | null }) {
  if (!value) return <div><span>{label}</span><strong>—</strong></div>;
  return <div><span>{label}</span><strong>{value.code ?? value.driverNumber} · P{value.position ?? "—"}</strong><small>{value.gapSeconds == null ? "—" : `${value.gapSeconds.toFixed(3)}s`}</small></div>;
}

function PitHistory({ events }: { events: PitEvent[] }) {
  if (events.length === 0) return <div className="panel-empty">NO OBSERVED PIT EVENTS AT THIS REPLAY TIME</div>;
  return <div className="pit-history-list">{events.map((event) => <div key={`${event.sequence}-${event.lap}`}>
    <strong>LAP {event.lap}</strong>
    <CompoundTransition from={event.previousCompound} to={event.newCompound} compact />
    <span><small>STOP</small><b>{event.stopDuration == null ? "—" : `${event.stopDuration.toFixed(1)}s`}</b></span>
    <span><small>PIT LANE</small><b>{event.pitLaneDuration == null ? "—" : `${event.pitLaneDuration.toFixed(1)}s`}</b></span>
  </div>)}</div>;
}

export function DriverFocusView({ state, analytics, driverNumber, history, historyError, playhead, positionMode, onChangeDriver, onBack }: {
  state: RaceState;
  analytics: AnalyticsSnapshot | null;
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
        <div className="driver-battle-context"><BattleContext label="AHEAD" value={model?.ahead ?? null} /><BattleContext label="BEHIND" value={model?.behind ?? null} /></div>
      </section>
      <div className="driver-map-context"><TrackMap circuit={state.circuit} session={state.session} drivers={allDrivers} positionMode={positionMode} /></div>
      <StrategyOutlook analytics={analytics} driverNumber={driverNumber} driverStatus={driver.status} />
      <Panel eyebrow="PACE DELTA" title="Stint trend" className="driver-history-panel" action={<span className="pace-baseline-badge">VS CLEAN STINT BASELINE <InfoPopover meaning="Signed lap-time delta versus the robust median of representative laps in the same stint. Faster laps are above zero; slower laps are below." why="Pit, neutralized, contaminated, and robust outlier laps do not set the chart scale. They remain visible as capped grey hatched markers." /></span>}>
        {historyError && <div className="panel-empty">HISTORY UNAVAILABLE · {historyError}</div>}
        {!historyError && !history && !model && <div className="panel-empty">LOADING NORMALIZED LAP EVIDENCE</div>}
        <PaceDeltaChart samples={paceSamples} serverScale={model?.pace.scale} />
      </Panel>
      <Panel eyebrow="FACTUAL" title="Pit history" className="pit-history-panel"><PitHistory events={pitEvents} /></Panel>
    </div>
  </div>;
}
