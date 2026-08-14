import { useMemo, type CSSProperties } from "react";

import { StrategyOutlook } from "../components/analysis/StrategyOutlook";
import { TrackMap } from "../components/analysis/TrackMap";
import { DataValue } from "../components/shared/DataValue";
import { Panel } from "../components/shared/Panel";
import type { DriverHistory, PositionMode, RaceState } from "../domain/protocol";

function lapDuration(seconds: number | null) {
  if (seconds == null) return "-";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds % 60).toFixed(3).padStart(6, "0")}`;
}

export function DriverFocusView({ state, driverNumber, history, historyError, playhead, positionMode, onBack }: {
  state: RaceState;
  driverNumber: string;
  history: DriverHistory | null;
  historyError: string | null;
  playhead: string | null;
  positionMode: PositionMode;
  onBack: () => void;
}) {
  const driver = state.drivers[driverNumber] ?? null;
  const observations = useMemo(() => (history?.observations ?? []).filter((item) => !playhead || Date.parse(item.occurredAt) <= Date.parse(playhead)), [history?.observations, playhead]);
  const recent = observations.slice(-10).reverse();
  const pitLaps = observations.filter((item) => item.pit_in || item.pit_out);
  if (!driver) return <div className="driver-focus-view"><header className="experience-heading"><button onClick={onBack}>BACK TO SESSION</button><div><span>DRIVER FOCUS</span><h1>Driver unavailable</h1></div></header><div className="service-unavailable"><strong>DRIVER STATE UNAVAILABLE</strong><p>This driver is not present at the current replay time.</p></div></div>;
  const allDrivers = Object.values(state.drivers);
  return <div className="driver-focus-view">
    <header className="driver-hero" style={{ "--team": `#${driver.team_colour ?? "77808f"}` } as CSSProperties}><button onClick={onBack}>BACK TO SESSION</button><div className="driver-number">{driver.number}</div><div><span>DRIVER FOCUS · LAP {driver.lap ?? state.session.lap ?? "-"}</span><h1>{driver.name ?? driver.code ?? `Driver ${driver.number}`}</h1><p>{driver.team ?? "Team unavailable"}</p></div><div className="driver-hero-position"><span>CURRENT POSITION</span><strong>P{driver.position ?? "-"}</strong><DataValue compact value={driver.position === 1 ? "LEADER" : driver.gap_to_leader} availability={driver.availability.gap_to_leader} /></div></header>
    <div className="driver-focus-grid">
      <section className="driver-current panel"><header className="panel-heading"><div className="panel-title"><h2>Current stint</h2><span className="eyebrow">FACTUAL</span></div></header><div className="driver-current-metrics"><div><span>COMPOUND</span><strong>{driver.compound ?? "-"}</strong></div><div><span>TYRE AGE</span><strong>{driver.tyre_age == null ? "-" : `${driver.tyre_age} LAPS`}</strong></div><div><span>STINT LAPS</span><strong>{driver.stint_laps ?? "-"}</strong></div><div><span>PIT STOPS</span><strong>{driver.pit_count}</strong></div><div><span>LAST LAP</span><DataValue compact value={driver.last_lap} availability={driver.availability.last_lap} /></div><div><span>BEST LAP</span><DataValue compact value={driver.best_lap} availability={driver.availability.best_lap} /></div></div></section>
      <div className="driver-map-context"><TrackMap circuit={state.circuit} session={state.session} drivers={allDrivers} positionMode={positionMode} /></div>
      <StrategyOutlook />
      <Panel eyebrow="NORMALIZED EVIDENCE" title="Lap & stint history" className="driver-history-panel">
        {historyError && <div className="panel-empty">HISTORY UNAVAILABLE · {historyError}</div>}
        {!historyError && !history && <div className="panel-empty">LOADING NORMALIZED LAP EVIDENCE</div>}
        {history && recent.length === 0 && <div className="panel-empty">NO COMPLETED LAP EVIDENCE AT THIS REPLAY TIME</div>}
        {recent.length > 0 && <div className="lap-history-table"><header><span>LAP</span><span>TIME</span><span>TYRE</span><span>STINT</span><span>QUALITY</span></header>{recent.map((lap) => <div key={`${lap.sequence}-${lap.lap}`}><strong>{lap.lap}</strong><span>{lapDuration(lap.duration)}</span><span>{lap.compound ?? "-"} · {lap.tyre_age ?? "-"}L</span><span>{lap.stint_number ?? "-"}</span><i className={`quality-${lap.quality}`}>{lap.quality.toUpperCase()}</i></div>)}</div>}
      </Panel>
      <Panel eyebrow="FACTUAL" title="Pit history" className="pit-history-panel">{pitLaps.length === 0 ? <div className="panel-empty">NO PIT-IN / PIT-OUT EVIDENCE AT THIS REPLAY TIME</div> : <div className="pit-history-list">{pitLaps.map((lap) => <div key={`${lap.sequence}-${lap.lap}`}><strong>LAP {lap.lap}</strong><span>{lap.pit_in ? "PIT IN" : ""}{lap.pit_in && lap.pit_out ? " / " : ""}{lap.pit_out ? "PIT OUT" : ""}</span><small>{lap.compound ?? "COMPOUND UNKNOWN"}</small></div>)}</div>}</Panel>
    </div>
  </div>;
}
