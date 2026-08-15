import { useMemo, type CSSProperties } from "react";

import { StrategyOutlook } from "../components/analysis/StrategyOutlook";
import { TrackMap } from "../components/analysis/TrackMap";
import { DataValue } from "../components/shared/DataValue";
import { Panel } from "../components/shared/Panel";
import type { AnalyticsSnapshot, DriverBattleContext, DriverHistory, PaceSample, PitEvent, PositionMode, RaceState } from "../domain/protocol";

function lapDuration(seconds: number | null) {
  if (seconds == null) return "—";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds % 60).toFixed(3).padStart(6, "0")}`;
}

function PaceChart({ samples }: { samples: PaceSample[] }) {
  const deltas = samples.flatMap((sample) => sample.delta == null ? [] : [Math.abs(sample.delta)]);
  const scale = Math.max(1, ...deltas);
  if (samples.length === 0) return <div className="panel-empty">PACE EVIDENCE · UNKNOWN AT THIS REPLAY TIME</div>;
  return <div className="pace-chart" role="img" aria-label="Pace delta by lap">
    <div className="pace-zero" />
    <div className="pace-bars">{samples.map((sample) => {
      const magnitude = sample.delta == null ? 8 : Math.max(5, Math.min(86, (Math.abs(sample.delta) / scale) * 72));
      const title = `Lap ${sample.lap} · ${lapDuration(sample.rawLapTime)} · ${sample.delta == null ? "delta unknown" : `${sample.delta >= 0 ? "+" : ""}${sample.delta.toFixed(3)}s`} · ${sample.compound ?? "compound unknown"} · age ${sample.tyreAge ?? "—"} · ${sample.quality}${sample.contaminationReasons.length ? ` · ${sample.contaminationReasons.join(", ")}` : ""}`;
      return <div className={`pace-bar quality-${sample.quality} compound-bar-${(sample.compound ?? "unknown").toLowerCase()}`} key={`${sample.lap}-${sample.stintNumber}`} title={title}><i style={{ height: `${magnitude}%` }} /><span>{sample.lap}</span></div>;
    })}</div>
  </div>;
}

function BattleContext({ label, value }: { label: string; value: DriverBattleContext | null }) {
  return <div><span>{label}</span><strong>{value ? `${value.code ?? value.driverNumber} · P${value.position ?? "—"}` : "—"}</strong><small>{value?.gapSeconds == null ? "GAP UNKNOWN" : `${value.gapSeconds.toFixed(3)}s`}</small></div>;
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
  return <div className="driver-focus-view">
    <header className="driver-hero" style={{ "--team": `#${driver.team_colour ?? "77808f"}` } as CSSProperties}><button onClick={onBack}>BACK TO SESSION</button><button className="change-driver" onClick={onChangeDriver}>CHANGE DRIVER</button><div className="driver-number">{driver.number}</div><div><span>DRIVER FOCUS · LAP {driver.lap ?? state.session.lap ?? "—"}</span><h1>{driver.name ?? driver.code ?? `Driver ${driver.number}`}</h1><p>{driver.team ?? "Team unavailable"}</p></div><div className="driver-hero-position"><span>CURRENT POSITION</span><strong>P{driver.position ?? "—"}</strong><DataValue compact value={driver.position === 1 ? "LEADER" : driver.gap_to_leader} availability={driver.availability.gap_to_leader} /></div></header>
    <div className="driver-focus-grid">
      <section className="driver-current panel"><header className="panel-heading"><div className="panel-title"><h2>Current stint</h2><span className="eyebrow">FACTUAL</span></div></header><div className="driver-current-metrics"><div><span>COMPOUND</span><strong>{driver.compound ?? "—"}</strong></div><div><span>TYRE AGE</span><strong>{driver.tyre_age == null ? "—" : `${driver.tyre_age} LAPS`}</strong></div><div><span>STINT LAPS</span><strong>{driver.stint_laps ?? "—"}</strong></div><div><span>PIT STOPS</span><strong>{driver.pit_count}</strong></div><div><span>LAST LAP</span><DataValue compact value={driver.last_lap} availability={driver.availability.last_lap} /></div><div><span>BEST LAP</span><DataValue compact value={driver.best_lap} availability={driver.availability.best_lap} /></div></div><div className="driver-battle-context"><BattleContext label="AHEAD" value={model?.ahead ?? null} /><BattleContext label="BEHIND" value={model?.behind ?? null} /></div></section>
      <div className="driver-map-context"><TrackMap circuit={state.circuit} session={state.session} drivers={allDrivers} positionMode={positionMode} /></div>
      <StrategyOutlook analytics={analytics} driverNumber={driverNumber} />
      <Panel eyebrow="PACE DELTA" title="Stint trend" className="driver-history-panel" action={<span className="panel-badge">CLEAN-STINT MEDIAN · MAD V1</span>}>
        {historyError && <div className="panel-empty">HISTORY UNAVAILABLE · {historyError}</div>}
        {!historyError && !history && !model && <div className="panel-empty">LOADING NORMALIZED LAP EVIDENCE</div>}
        <PaceChart samples={paceSamples} />
      </Panel>
      <Panel eyebrow="FACTUAL" title="Pit history" className="pit-history-panel">{pitEvents.length === 0 ? <div className="panel-empty">NO OBSERVED PIT EVENTS AT THIS REPLAY TIME</div> : <div className="pit-history-list">{pitEvents.map((event) => <div key={`${event.sequence}-${event.lap}`}><strong>LAP {event.lap}</strong><span>{event.previousCompound ?? "—"} → {event.newCompound ?? "—"}</span><small>STOP {event.stopDuration == null ? "—" : `${event.stopDuration.toFixed(1)}s`} · PIT LANE {event.pitLaneDuration == null ? "—" : `${event.pitLaneDuration.toFixed(1)}s`}</small></div>)}</div>}</Panel>
    </div>
  </div>;
}
